"""Requirement Agent — 需求澄清，产出 PRD（不可变锚点）."""

from __future__ import annotations

import json
from typing import Any

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import PRD, Session, Stage


class RequirementAgent(BaseAgent):
    """需求澄清 Agent.

    通过多轮对话或与 LLM 交互，将用户的原始需求转化为结构化的 PRD。
    PRD 一旦生成，作为整个链路的不可变锚点。
    """

    stage = Stage.CLARIFY
    name = "requirement"

    SYSTEM_PROMPT = """你是一个专业的需求分析师。你的任务是将用户的原始需求转化为清晰、完整、无歧义的结构化需求文档（PRD）。

你需要输出 JSON 格式：
{
  "clarified_requirement": "用一句话清晰描述需求",
  "functional_requirements": ["功能点1", "功能点2", ...],
  "non_functional_requirements": ["性能要求", "安全要求", ...],
  "constraints": ["技术约束", "业务约束", ...],
  "assumptions": ["假设前提1", "假设前提2", ...]
}

要求：
- 功能点必须覆盖用户提到的所有功能，不能遗漏
- 如果需求有歧义，基于最合理的假设进行澄清并在 assumptions 中说明
- 输出必须是可以直接用于后续技术方案的完整需求
"""

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        raw_requirement = kwargs.get("requirement", "")
        if not raw_requirement:
            return AgentResult(success=False, message="No requirement provided.")

        user_prompt = f"原始需求：\n{raw_requirement}\n\n请将其转化为结构化的 PRD。"

        response = await self.llm.chat_with_system(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response)
            prd = PRD(
                raw_requirement=raw_requirement,
                clarified_requirement=data.get("clarified_requirement", ""),
                functional_requirements=data.get("functional_requirements", []),
                non_functional_requirements=data.get("non_functional_requirements", []),
                constraints=data.get("constraints", []),
                assumptions=data.get("assumptions", []),
            )
            session.prd = prd

            # 保存上下文摘要
            summary = f"需求：{prd.clarified_requirement}\n功能点：{', '.join(prd.functional_requirements[:5])}"
            session.update_summary(summary)
            self.memory.save_session_context(session.id, {"prd": prd.model_dump()}, summary)

            return AgentResult(
                success=True,
                output={"prd": prd.model_dump()},
                message=f"PRD generated with {len(prd.functional_requirements)} functional requirements.",
            )
        except json.JSONDecodeError as e:
            return AgentResult(success=False, message=f"Failed to parse PRD: {e}", should_retry=True)
