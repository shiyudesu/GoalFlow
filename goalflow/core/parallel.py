"""多 Agent 并行执行支持 — Phase 4 增强."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Task, TaskStatus


class ParallelExecutor:
    """并行执行器.

    支持多个 Agent/任务并行执行，提升效率。
    例如：多个 Coding Agent 并行处理不同模块。
    """

    def __init__(self, max_concurrency: int = 3) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def run_agent(
        self,
        agent: BaseAgent,
        session: Session,
        **kwargs: Any,
    ) -> AgentResult:
        """在信号量控制下运行单个 Agent."""
        async with self.semaphore:
            return await agent.run(session, **kwargs)

    async def run_agents(
        self,
        agents: List[BaseAgent],
        session: Session,
        **kwargs: Any,
    ) -> List[AgentResult]:
        """并行运行多个 Agent."""
        tasks = [self.run_agent(agent, session, **kwargs) for agent in agents]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run_tasks(
        self,
        agent: BaseAgent,
        session: Session,
        task_filter: Callable[[Task], bool],
        **kwargs: Any,
    ) -> List[AgentResult]:
        """对符合条件的任务并行执行.

        为每个任务创建 Agent 的独立运行上下文。
        """
        filtered_tasks = [t for t in session.tasks if task_filter(t)]
        if not filtered_tasks:
            return []

        # 为每个任务创建一个运行调用
        async def run_for_task(task: Task) -> AgentResult:
            async with self.semaphore:
                task.status = TaskStatus.IN_PROGRESS
                result = await agent.run(session, task_id=task.id, **kwargs)
                return result

        coros = [run_for_task(t) for t in filtered_tasks]
        return await asyncio.gather(*coros, return_exceptions=True)
