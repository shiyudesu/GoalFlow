"""Self-Check Agent — 一致性校验，防止目标漂移.

这是 GoalFlow 防漂移机制的核心组件：
- 检查当前产出是否覆盖 PRD 所有功能点
- 检查是否有任务被跳过、简化或遗漏
- 生成偏差报告，有偏差则打回重试
"""

from __future__ import annotations

import json
from typing import Any

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Event, EventType, Session, Stage


class SelfCheckAgent(BaseAgent):
    """自检 Agent.

    独立运行，不隶属于任何阶段，可在任意阶段完成后介入。
    """

    stage = Stage.INIT  # 不属于特定阶段
    name = "self_check"

    SYSTEM_PROMPT = """你是一个严格的质量检查员。你的任务是检查当前阶段的产出是否与原始需求（PRD）一致，是否有遗漏或偏差。

你需要输出 JSON 格式：
{
  "consistent": true|false,
  "coverage_score": 0-100,
  "missing_items": ["遗漏的功能点1", "遗漏的功能点2"],
  "deviations": ["偏差描述1", "偏差描述2"],
  "skipped_tasks": ["被跳过的任务标题"],
  "recommendation": "建议措施"
}

严格要求：
- coverage_score < 90 视为不合格
- 任何 functional requirement 未被覆盖都必须列出
- 任何任务被简化或跳过都必须列出
- 必须诚实、严格，不能为了通过检查而降低标准
"""

    async def check_stage(
        self,
        session: Session,
        stage: Stage,
        stage_output: dict,
    ) -> AgentResult:
        """对指定阶段的产出进行一致性校验."""
        if not session.prd:
            return AgentResult(success=False, message="No PRD to check against.")

        # 构建待检查内容
        stage_tasks = [t for t in session.tasks if t.stage == stage]
        tasks_summary = "\n".join([
            f"- {t.title} (status: {t.status.value}, dod: {t.dod})"
            for t in stage_tasks
        ])

        user_prompt = (
            f"PRD 锚点：\n{session.prd.to_anchor_text()}\n\n"
            f"当前阶段：{stage.value}\n"
            f"阶段产出：\n{json.dumps(stage_output, indent=2)[:3000]}\n\n"
            f"本阶段任务：\n{tasks_summary}\n\n"
            "请进行严格的一致性校验。"
        )

        response = await self.llm.chat_with_system(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response)
            consistent = data.get("consistent", False)
            coverage_score = data.get("coverage_score", 0)
            missing = data.get("missing_items", [])
            deviations = data.get("deviations", [])
            skipped = data.get("skipped_tasks", [])

            # 发布一致性校验事件
            await self._publish_event(
                session,
                EventType.CONSISTENCY_CHECK_FAILED if not consistent else EventType.STAGE_COMPLETED,
                {
                    "stage": stage.value,
                    "consistent": consistent,
                    "coverage_score": coverage_score,
                    "missing": missing,
                    "deviations": deviations,
                    "skipped": skipped,
                },
            )

            if not consistent or coverage_score < 90:
                return AgentResult(
                    success=False,
                    message=f"Consistency check FAILED (score: {coverage_score}). Missing: {missing}. Deviations: {deviations}",
                    should_retry=True,
                    output=data,
                )

            return AgentResult(
                success=True,
                message=f"Consistency check PASSED (score: {coverage_score}).",
                output=data,
            )
        except json.JSONDecodeError as e:
            return AgentResult(success=False, message=f"Self-check parse error: {e}", should_retry=True)

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        """基类要求实现，但 SelfCheck 通常通过 check_stage 调用."""
        stage = kwargs.get("stage", Stage.PLAN)
        output = kwargs.get("stage_output", {})
        return await self.check_stage(session, stage, output)
