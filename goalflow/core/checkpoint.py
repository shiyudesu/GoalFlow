"""Human Checkpoint Gate — 人工介入控制."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from .models import Event, EventType, Session, Stage


console = Console()


class CheckpointGate:
    """人工检查点门控.

    每个阶段完成后，根据配置决定是否暂停等待人工介入。
    """

    def __init__(
        self,
        input_handler: Optional[Callable[[str, Session], Any]] = None,
    ) -> None:
        self.input_handler = input_handler or self._default_input_handler

    async def check(
        self,
        session: Session,
        stage: Stage,
        stage_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """检查当前阶段是否需要人工介入.

        Returns:
            可能已被用户修改的 stage_output。
        """
        mode = session.checkpoint_config.get(stage, "auto")

        if mode == "auto":
            console.print(f"[dim][Checkpoint] Stage '{stage.value}' in auto mode, continuing...[/dim]")
            return stage_output

        # manual 模式：暂停等待用户
        console.print(Panel(
            f"[bold yellow]Human Checkpoint: {stage.value.upper()}[/bold yellow]\n\n"
            f"Session: {session.id}\n"
            f"Repository: {session.repo_path}\n\n"
            f"Stage output preview:\n{self._preview_output(stage_output)}\n\n"
            "Options:\n"
            "  [c]ontinue — accept and proceed\n"
            "  [e]dit — modify stage output (follow prompt)\n"
            "  [r]edo — rerun this stage\n"
            "  [b]acktrack — go back to planning\n",
            title="GoalFlow",
        ))

        choice = Prompt.ask(
            "Your choice",
            choices=["c", "e", "r", "b"],
            default="c",
        )

        if choice == "c":
            return stage_output
        elif choice == "e":
            return await self._handle_edit(session, stage, stage_output)
        elif choice == "r":
            return {"_checkpoint_action": "redo"}
        elif choice == "b":
            return {"_checkpoint_action": "backtrack"}

        return stage_output

    def _preview_output(self, output: Dict[str, Any], max_len: int = 800) -> str:
        """生成阶段输出的预览文本."""
        text = str(output)
        if len(text) > max_len:
            text = text[:max_len] + "\n... (truncated)"
        return text

    async def _handle_edit(
        self,
        session: Session,
        stage: Stage,
        output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """处理用户编辑."""
        console.print("[dim]Enter your edit as a natural language instruction (or JSON for structured data):[/dim]")
        user_input = Prompt.ask("Edit instruction")
        if self.input_handler:
            result = self.input_handler(user_input, session)
            if asyncio.iscoroutinefunction(self.input_handler):
                result = await result
            if isinstance(result, dict):
                output.update(result)
            else:
                output["_user_edit"] = str(result)
        else:
            output["_user_edit"] = user_input
        return output

    def _default_input_handler(self, user_input: str, session: Session) -> str:
        """默认输入处理器."""
        return user_input
