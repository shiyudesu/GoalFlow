"""FastAPI 应用 — 提供 REST API 和 SSE 实时事件流."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from goalflow.core.checkpoint import CheckpointGate
from goalflow.core.event_bus import EventBus
from goalflow.core.models import Event, EventType, Session, Stage
from goalflow.core.session_manager import SessionManager
from goalflow.core.state_machine import WorkflowStateMachine
from goalflow.agents import (
    CodingAgent,
    DeployAgent,
    ModuleLocatorAgent,
    PlanningAgent,
    RequirementAgent,
    SelfCheckAgent,
    TestingAgent,
)
from goalflow.github.client import GitHubClient
from goalflow.llm.client import LLMClient
from goalflow.memory.store import MemoryStore

app = FastAPI(title="GoalFlow API", version="0.1.0")

# 全局状态
_sessions: Dict[str, Session] = {}
_event_buses: Dict[str, EventBus] = {}
_session_manager = SessionManager()


class CreateSessionRequest(BaseModel):
    repo_path: str
    requirement: str
    github_token: Optional[str] = None
    model: Optional[str] = "gpt-4o"
    auto_mode: bool = True


class SessionResponse(BaseModel):
    id: str
    repo_path: str
    current_stage: str
    created_at: str


class TaskResponse(BaseModel):
    id: str
    title: str
    status: str
    stage: str
    attempts: int
    max_attempts: int


def get_llm_client(model: str = "gpt-4o") -> LLMClient:
    return LLMClient(
        model=model,
        api_key=os.getenv("GOALFLOW_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("GOALFLOW_BASE_URL"),
    )


@app.post("/sessions", response_model=SessionResponse)
async def create_session(req: CreateSessionRequest) -> SessionResponse:
    """创建新 Session 并启动工作流."""
    session = Session(
        repo_path=req.repo_path,
        github_token=req.github_token,
    )
    event_bus = EventBus()
    _sessions[session.id] = session
    _event_buses[session.id] = event_bus

    # 启动工作流（后台）
    asyncio.create_task(_run_workflow_background(session, req, event_bus))

    return SessionResponse(
        id=session.id,
        repo_path=session.repo_path,
        current_stage=session.current_stage.value,
        created_at=session.created_at.isoformat(),
    )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """获取 Session 详情."""
    session = _sessions.get(session_id) or _session_manager.load(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "repo_path": session.repo_path,
        "current_stage": session.current_stage.value,
        "tasks": [t.model_dump() for t in session.tasks],
        "stage_outputs": {k.value: v for k, v in session.stage_outputs.items()},
        "checkpoint_config": {k.value: v for k, v in session.checkpoint_config.items()},
        "created_at": session.created_at.isoformat(),
    }


@app.get("/sessions/{session_id}/events")
async def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    """获取 Session 事件历史."""
    event_bus = _event_buses.get(session_id)
    if not event_bus:
        raise HTTPException(status_code=404, detail="Session not found")
    events = event_bus.get_history(session_id=session_id)
    return [e.model_dump() for e in events]


@app.get("/sessions/{session_id}/stream")
async def stream_events(session_id: str) -> StreamingResponse:
    """SSE 实时事件流."""
    event_bus = _event_buses.get(session_id)
    if not event_bus:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # 发送历史事件
        for event in event_bus.get_history(session_id=session_id):
            yield f"data: {json.dumps(event.model_dump())}\n\n"

        # 订阅新事件（简化实现：轮询）
        last_count = len(event_bus.get_history(session_id=session_id))
        while True:
            await asyncio.sleep(1)
            events = event_bus.get_history(session_id=session_id)
            if len(events) > last_count:
                for event in events[last_count:]:
                    yield f"data: {json.dumps(event.model_dump())}\n\n"
                last_count = len(events)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/checkpoint/{stage}")
async def checkpoint_response(
    session_id: str,
    stage: str,
    action: str = Query(..., pattern="^(continue|redo|backtrack)$"),
    feedback: Optional[str] = None,
) -> Dict[str, Any]:
    """响应当前阶段的人工检查点."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 将用户反馈存入 session，供 checkpoint gate 读取
    session.stage_outputs[Stage(stage)] = session.stage_outputs.get(Stage(stage), {})
    session.stage_outputs[Stage(stage)]["_checkpoint_action"] = action
    if feedback:
        session.stage_outputs[Stage(stage)]["_user_feedback"] = feedback

    return {"status": "ok", "action": action}


@app.get("/sessions")
async def list_sessions() -> List[Dict[str, str]]:
    """列出所有 Session."""
    return _session_manager.list_sessions()


async def _run_workflow_background(
    session: Session,
    req: CreateSessionRequest,
    event_bus: EventBus,
) -> None:
    """后台运行工作流."""
    llm = get_llm_client(req.model or "gpt-4o")
    memory = MemoryStore()
    checkpoint_gate = CheckpointGate()

    agents = {
        Stage.CLARIFY: RequirementAgent(llm, event_bus, memory),
        Stage.PLAN: PlanningAgent(llm, event_bus, memory),
        Stage.LOCATE: ModuleLocatorAgent(llm, event_bus, memory),
        Stage.CODE: CodingAgent(llm, event_bus, memory),
        Stage.TEST: TestingAgent(llm, event_bus, memory),
        Stage.DEPLOY: DeployAgent(llm, event_bus, memory),
    }
    self_check = SelfCheckAgent(llm, event_bus, memory)

    if session.github_token:
        gh_client = GitHubClient(session.github_token)
        agents[Stage.DEPLOY].github = gh_client

    sm = WorkflowStateMachine(session)

    for stage in Stage:
        session.checkpoint_config[stage] = "auto" if req.auto_mode else "manual"

    # 简化版工作流（与 CLI 类似但适配后台运行）
    stages_to_run = [
        (Stage.CLARIFY, lambda: agents[Stage.CLARIFY].run(session, requirement=req.requirement)),
        (Stage.PLAN, lambda: agents[Stage.PLAN].run(session)),
        (Stage.LOCATE, lambda: agents[Stage.LOCATE].run(session)),
        (Stage.CODE, lambda: agents[Stage.CODE].run(session)),
        (Stage.TEST, lambda: agents[Stage.TEST].run(session)),
        (Stage.DEPLOY, lambda: agents[Stage.DEPLOY].run(session)),
    ]

    for stage, agent_call in stages_to_run:
        try:
            result = await agent_call()
            _session_manager.save(session)

            if not result.success and not result.should_retry:
                break
        except Exception as e:
            await event_bus.publish(Event(
                session_id=session.id,
                type=EventType.STAGE_FAILED,
                stage=stage,
                payload={"error": str(e)},
            ))
            break


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
