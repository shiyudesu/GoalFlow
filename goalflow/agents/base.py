"""Agent 基类."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel

from goalflow.core.models import Event, EventType, Session, Stage
from goalflow.core.event_bus import EventBus
from goalflow.llm.client import LLMClient
from goalflow.memory.store import MemoryStore


class AgentResult(BaseModel):
    """Agent 执行结果."""

    success: bool = True
    output: Dict[str, Any] = {}
    message: str = ""
    should_retry: bool = False
    should_escalate: bool = False


class BaseAgent(ABC):
    """Agent 基类.

    所有阶段 Agent 的抽象基类，统一接口。
    """

    stage: Stage = Stage.INIT
    name: str = "base"

    def __init__(
        self,
        llm: LLMClient,
        event_bus: EventBus,
        memory: MemoryStore,
    ) -> None:
        self.llm = llm
        self.event_bus = event_bus
        self.memory = memory

    async def run(self, session: Session, **kwargs: Any) -> AgentResult:
        """运行 Agent.

        子类可覆盖此方法，但建议覆盖 _execute 以复用事件发布逻辑。
        """
        await self._publish_event(session, EventType.STAGE_STARTED)

        try:
            result = await self._execute(session, **kwargs)
            if result.success:
                await self._publish_event(session, EventType.STAGE_COMPLETED, {"message": result.message})
            else:
                await self._publish_event(session, EventType.STAGE_FAILED, {"message": result.message, "should_retry": result.should_retry})
            return result
        except Exception as e:
            await self._publish_event(session, EventType.STAGE_FAILED, {"error": str(e)})
            return AgentResult(success=False, message=str(e), should_retry=True)

    @abstractmethod
    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        """子类实现的具体执行逻辑."""
        ...

    async def _publish_event(
        self,
        session: Session,
        event_type: EventType,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发布事件."""
        event = Event(
            session_id=session.id,
            type=event_type,
            stage=self.stage,
            payload=payload or {},
        )
        await self.event_bus.publish(event)
