"""Coding Agent — 按模块映射生成/修改代码."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Stage, Task, TaskStatus


class CodingAgent(BaseAgent):
    """代码生成 Agent.

    根据模块定位和任务列表，生成代码变更（diff 形式）。
    支持读取现有文件、生成修改、输出统一格式的代码变更。
    """

    stage = Stage.CODE
    name = "coding"

    SYSTEM_PROMPT = """你是一个资深软件工程师。你的任务是根据任务描述和模块定位，生成精确的代码变更。

你必须输出 JSON 格式：
{
  "changes": [
    {
      "file_path": "文件路径",
      "action": "create|modify|delete",
      "reasoning": "变更理由",
      "content": "完整的文件内容（create/modify）",
      "search_block": "用于定位的代码片段（modify时使用，必须精确匹配原文）",
      "replace_block": "替换后的代码片段（modify时使用）"
    }
  ]
}

严格要求：
1. modify 时必须提供精确的 search_block，确保可以安全替换
2. 代码必须遵循项目现有的编码风格和命名规范
3. 不要省略任何细节，必须提供完整的文件内容（create）或精确的替换块（modify）
4. 如果一个任务涉及多个文件，列出所有变更
"""

    def _read_file(self, repo_path: str, file_path: str) -> str:
        """读取文件内容."""
        try:
            full_path = Path(repo_path) / file_path
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        code_tasks = [t for t in session.tasks if t.stage == Stage.CODE and t.status != TaskStatus.COMPLETED]

        if not code_tasks:
            # 标记 code 阶段完成
            session.stage_outputs[Stage.CODE] = {"changes": [], "message": "No code tasks pending."}
            return AgentResult(success=True, message="No pending code tasks.")

        all_changes = []

        for task in code_tasks:
            task.mark_attempt()
            target_files = task.metadata.get("target_files", [])

            # 读取目标文件内容
            file_contents = {}
            for fp in target_files:
                content = self._read_file(session.repo_path, fp)
                file_contents[fp] = content[:4000] if content else "(file does not exist yet)"  # 限制长度

            user_prompt = (
                f"任务：{task.title}\n"
                f"描述：{task.description}\n"
                f"DoD：{task.dod}\n"
                f"PRD 锚点：\n{session.prd.to_anchor_text() if session.prd else 'N/A'}\n\n"
                f"目标文件：\n"
            )
            for fp, content in file_contents.items():
                user_prompt += f"\n--- {fp} ---\n{content}\n"

            user_prompt += "\n请生成代码变更。"

            response = await self.llm.chat_with_system(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )

            try:
                data = json.loads(response)
                changes = data.get("changes", [])
                all_changes.extend(changes)

                # 验证：变更是否非空
                if changes:
                    task.status = TaskStatus.COMPLETED
                    task.result = json.dumps(changes)
                else:
                    task.status = TaskStatus.FAILED
                    task.error = "No changes generated"
            except json.JSONDecodeError as e:
                task.status = TaskStatus.FAILED
                task.error = f"Parse error: {e}"

        # 检查是否所有 code 任务都已完成
        pending = [t for t in session.tasks if t.stage == Stage.CODE and t.status != TaskStatus.COMPLETED]
        if pending:
            failed = [t for t in pending if t.status == TaskStatus.FAILED]
            retryable = [t for t in pending if t.can_retry()]
            return AgentResult(
                success=len(failed) == 0 and len(retryable) == 0,
                message=f"{len(pending)} code tasks pending ({len(failed)} failed, {len(retryable)} retryable).",
                should_retry=len(retryable) > 0,
            )

        session.stage_outputs[Stage.CODE] = {"changes": all_changes}

        return AgentResult(
            success=True,
            output={"changes": all_changes},
            message=f"Generated {len(all_changes)} code changes.",
        )
