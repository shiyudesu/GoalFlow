"""Module Locator Agent — 分析代码库，定位修改点."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Stage, Task, TaskStatus


class ModuleLocatorAgent(BaseAgent):
    """模块定位 Agent.

    分析现有代码库结构，确定每个任务对应的文件和模块边界。
    """

    stage = Stage.LOCATE
    name = "module_locator"

    SYSTEM_PROMPT = """你是一个代码库分析专家。你的任务是分析代码库结构，为每个任务定位需要修改的文件和模块。

你需要输出 JSON 格式：
{
  "module_map": [
    {
      "task_id": "任务ID",
      "target_files": ["文件路径1", "文件路径2"],
      "reasoning": "选择这些文件的理由",
      "affected_modules": ["模块A", "模块B"]
    }
  ],
  "additional_files_to_read": ["需要深入阅读的文件路径"]
}

要求：
- 必须基于实际的文件树进行分析
- 每个任务至少对应一个具体文件
- 给出选择文件的理由
- 识别可能的依赖影响和副作用
"""

    def _scan_repo(self, repo_path: str, max_depth: int = 4) -> List[str]:
        """扫描代码库文件树."""
        files = []
        root = Path(repo_path)
        for path in root.rglob("*"):
            if path.is_file():
                # 跳过常见非代码文件
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                if path.suffix in {".pyc", ".pyo", ".so", ".dylib", ".dll"}:
                    continue
                if path.name in {"node_modules", "__pycache__", "venv", ".venv"}:
                    continue
                rel = str(path.relative_to(root))
                parts = rel.split(os.sep)
                if len(parts) <= max_depth:
                    files.append(rel)
        return sorted(files)

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        repo_path = session.repo_path
        if not Path(repo_path).exists():
            return AgentResult(success=False, message=f"Repo path not found: {repo_path}")

        # 扫描文件树
        file_tree = self._scan_repo(repo_path)

        # 保存 repo 索引
        self.memory.save_repo_index(repo_path, file_tree, {}, {})

        # 只处理 locate 阶段的任务
        locate_tasks = [t for t in session.tasks if t.stage == Stage.LOCATE]
        if not locate_tasks:
            # 如果没有专门的 locate 任务，为 code 阶段任务做定位
            locate_tasks = [t for t in session.tasks if t.stage == Stage.CODE]

        task_descriptions = []
        for t in locate_tasks:
            task_descriptions.append(f"- ID: {t.id}\n  Title: {t.title}\n  Desc: {t.description}\n  DoD: {t.dod}")

        user_prompt = (
            f"代码库路径：{repo_path}\n"
            f"文件树（前200个文件）：\n" + "\n".join(file_tree[:200]) + "\n\n"
            f"PRD 功能点：\n" + "\n".join(session.prd.functional_requirements if session.prd else []) + "\n\n"
            f"需要定位的任务：\n" + "\n".join(task_descriptions) + "\n\n"
            "请为每个任务定位目标文件和模块。"
        )

        response = await self.llm.chat_with_system(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response)
            module_map = data.get("module_map", [])

            # 将定位结果更新到任务中
            for mapping in module_map:
                task_id = mapping.get("task_id")
                for task in session.tasks:
                    if task.id == task_id:
                        task.metadata["target_files"] = mapping.get("target_files", [])
                        task.metadata["affected_modules"] = mapping.get("affected_modules", [])
                        task.metadata["reasoning"] = mapping.get("reasoning", "")
                        task.status = TaskStatus.COMPLETED

            # 标记所有 locate 阶段任务完成
            for task in session.tasks:
                if task.stage == Stage.LOCATE:
                    task.status = TaskStatus.COMPLETED

            session.stage_outputs[Stage.LOCATE] = {
                "module_map": module_map,
                "file_count": len(file_tree),
            }

            return AgentResult(
                success=True,
                output={"module_map": module_map, "file_tree": file_tree},
                message=f"Located modules for {len(module_map)} tasks across {len(file_tree)} files.",
            )
        except (json.JSONDecodeError, KeyError) as e:
            return AgentResult(success=False, message=f"Failed to parse module map: {e}", should_retry=True)
