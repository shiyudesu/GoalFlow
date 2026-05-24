"""Testing Agent — 生成/运行测试，产出测试报告."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, List

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Stage, Task, TaskStatus


class TestingAgent(BaseAgent):
    """测试 Agent.

    生成测试用例、运行测试、反馈结果。
    测试失败时必须修复，否则不前进。
    """

    stage = Stage.TEST
    name = "testing"

    SYSTEM_PROMPT = """你是一个测试专家。你的任务是为代码变更生成测试用例，并确保所有测试通过。

你需要输出 JSON 格式：
{
  "test_files": [
    {
      "file_path": "测试文件路径",
      "content": "完整的测试代码"
    }
  ],
  "test_plan": "测试策略简述"
}

要求：
- 测试必须覆盖 PRD 中的所有功能点
- 包含正常路径和边界情况
- 使用项目已有的测试框架
- 测试代码必须可以直接运行
"""

    def _detect_test_framework(self, repo_path: str) -> str:
        """检测测试框架."""
        root = Path(repo_path)
        if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
            return "pytest"
        if (root / "package.json").exists():
            return "jest"  # 或其他 JS 框架
        if any(f.name.startswith("test_") for f in root.rglob("*.py")):
            return "pytest"
        return "pytest"  # 默认

    def _run_tests(self, repo_path: str, test_path: str = "") -> dict:
        """运行测试."""
        framework = self._detect_test_framework(repo_path)
        cmd = []
        if framework == "pytest":
            cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
            if test_path:
                cmd.append(test_path)
        elif framework == "jest":
            cmd = ["npx", "jest", "--passWithNoTests"]
        else:
            return {"success": False, "stdout": "", "stderr": f"Unknown test framework: {framework}"}

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Test execution timeout", "returncode": -1}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        # 应用代码变更到工作目录（简化：直接写入文件）
        code_output = session.stage_outputs.get(Stage.CODE, {})
        changes = code_output.get("changes", [])

        # 写入变更
        for change in changes:
            fp = change.get("file_path", "")
            action = change.get("action", "")
            full_path = Path(session.repo_path) / fp
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if action == "create":
                full_path.write_text(change.get("content", ""), encoding="utf-8")
            elif action == "modify":
                original = full_path.read_text(encoding="utf-8") if full_path.exists() else ""
                search = change.get("search_block", "")
                replace = change.get("replace_block", "")
                if search in original:
                    new_content = original.replace(search, replace, 1)
                    full_path.write_text(new_content, encoding="utf-8")
                else:
                    # search_block 不匹配，标记失败
                    return AgentResult(
                        success=False,
                        message=f"Search block not found in {fp}",
                        should_retry=True,
                    )
            elif action == "delete":
                if full_path.exists():
                    full_path.unlink()

        # 生成测试
        test_tasks = [t for t in session.tasks if t.stage == Stage.TEST and t.status != TaskStatus.COMPLETED]

        all_test_files = []
        if test_tasks:
            user_prompt = (
                f"PRD：\n{session.prd.to_anchor_text() if session.prd else 'N/A'}\n\n"
                f"代码变更：\n{json.dumps(changes, indent=2)[:3000]}\n\n"
                "请生成测试用例。"
            )

            response = await self.llm.chat_with_system(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )

            try:
                data = json.loads(response)
                test_files = data.get("test_files", [])
                for tf in test_files:
                    fp = tf.get("file_path", "")
                    content = tf.get("content", "")
                    test_path = Path(session.repo_path) / fp
                    test_path.parent.mkdir(parents=True, exist_ok=True)
                    test_path.write_text(content, encoding="utf-8")
                    all_test_files.append(fp)

                for task in test_tasks:
                    task.status = TaskStatus.COMPLETED
            except json.JSONDecodeError as e:
                return AgentResult(success=False, message=f"Failed to parse tests: {e}", should_retry=True)

        # 运行测试
        test_result = self._run_tests(session.repo_path)

        if not test_result["success"]:
            # 测试失败：尝试修复
            return AgentResult(
                success=False,
                message=f"Tests failed:\n{test_result['stderr']}",
                should_retry=True,
            )

        session.stage_outputs[Stage.TEST] = {
            "test_files": all_test_files,
            "test_result": test_result,
        }

        return AgentResult(
            success=True,
            output={"test_files": all_test_files, "test_result": test_result},
            message="All tests passed.",
        )
