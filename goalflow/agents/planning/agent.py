"""Planning Agent — 方案拆解，生成原子任务列表 + DoD."""

from __future__ import annotations

import json
from typing import Any

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Stage, Task, TaskStatus


class PlanningAgent(BaseAgent):
    """方案拆解 Agent.

    将 PRD 拆解为可执行的原子任务列表，每个任务附带明确的 DoD。
    任务列表作为阻塞列表，未清空禁止进入下一阶段。
    """

    stage = Stage.PLAN
    name = "planning"

    SYSTEM_PROMPT = """你是一个资深架构师。你的任务是将需求文档（PRD）拆解为精确的原子级任务列表。

每个任务必须是"不可再分的最小单元"，例如：
- 修改某个特定函数的签名
- 为某个模块添加某个特定方法
- 编写某个函数的单元测试

你需要输出 JSON 格式：
{
  "technical_approach": "整体技术方案简述",
  "tasks": [
    {
      "title": "任务标题",
      "description": "详细描述",
      "dod": "完成定义（可客观验证的标准）",
      "stage": "plan|locate|code|test"
    }
  ]
}

严格要求：
1. 每个任务必须有明确、可客观验证的 DoD
2. 任务必须覆盖 PRD 中的所有功能点，不能遗漏
3. 任务按执行阶段分类（plan/locate/code/test）
4. 任务粒度要足够细，不能一个任务包含多个独立功能
"""

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        if not session.prd:
            return AgentResult(success=False, message="No PRD available. Run requirement clarification first.")

        user_prompt = (
            f"PRD:\n{session.prd.to_anchor_text()}\n\n"
            f"现有代码库路径：{session.repo_path}\n\n"
            "请将 PRD 拆解为原子任务列表。"
        )

        response = await self.llm.chat_with_system(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response)
            task_data_list = data.get("tasks", [])

            tasks = []
            for td in task_data_list:
                task = Task(
                    title=td["title"],
                    description=td.get("description", ""),
                    dod=td.get("dod", ""),
                    stage=Stage(td.get("stage", "plan")),
                    status=TaskStatus.PENDING,
                )
                tasks.append(task)

            session.tasks = tasks
            session.stage_outputs[Stage.PLAN] = {
                "technical_approach": data.get("technical_approach", ""),
                "task_count": len(tasks),
            }

            # 更新上下文摘要
            summary = (
                f"{session.context_summary}\n"
                f"方案：{data.get('technical_approach', '')}\n"
                f"任务数：{len(tasks)}"
            )
            session.update_summary(summary)

            return AgentResult(
                success=True,
                output={
                    "technical_approach": data.get("technical_approach", ""),
                    "tasks": [t.model_dump() for t in tasks],
                },
                message=f"Generated {len(tasks)} atomic tasks.",
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return AgentResult(success=False, message=f"Failed to parse plan: {e}", should_retry=True)
