"""GoalFlow CLI 入口."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from goalflow.core.checkpoint import CheckpointGate
from goalflow.core.event_bus import EventBus
from goalflow.core.models import EventType, Session, Stage
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


console = Console()


def get_llm_client() -> LLMClient:
    """从环境变量创建 LLM 客户端."""
    return LLMClient(
        model=os.getenv("GOALFLOW_MODEL", "gpt-4o"),
        api_key=os.getenv("GOALFLOW_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("GOALFLOW_BASE_URL"),
    )


async def run_workflow(
    session: Session,
    requirement: str,
    event_bus: EventBus,
    session_manager: SessionManager,
    checkpoint_gate: CheckpointGate,
    auto_mode: bool = True,
) -> None:
    """运行完整工作流."""

    llm = get_llm_client()
    memory = MemoryStore()

    # 初始化所有 Agent
    agents = {
        Stage.CLARIFY: RequirementAgent(llm, event_bus, memory),
        Stage.PLAN: PlanningAgent(llm, event_bus, memory),
        Stage.LOCATE: ModuleLocatorAgent(llm, event_bus, memory),
        Stage.CODE: CodingAgent(llm, event_bus, memory),
        Stage.TEST: TestingAgent(llm, event_bus, memory),
        Stage.DEPLOY: DeployAgent(llm, event_bus, memory),
    }
    self_check = SelfCheckAgent(llm, event_bus, memory)

    # 初始化 GitHub 客户端（如果有 token）
    if session.github_token:
        gh_client = GitHubClient(session.github_token)
        agents[Stage.DEPLOY].github = gh_client

    # 状态机
    sm = WorkflowStateMachine(session)

    # 配置检查点
    if auto_mode:
        for stage in Stage:
            session.checkpoint_config[stage] = "auto"
    else:
        for stage in Stage:
            session.checkpoint_config[stage] = "manual"

    console.print(Panel(
        f"[bold green]GoalFlow Session Started[/bold green]\n"
        f"ID: {session.id}\n"
        f"Repo: {session.repo_path}\n"
        f"Mode: {'auto' if auto_mode else 'manual'}\n"
        f"Model: {llm.model}",
        title="🚀 GoalFlow",
    ))

    # ===== STAGE 1: CLARIFY =====
    console.print("\n[bold blue]▶ Stage: CLARIFY[/bold blue]")
    sm.start_clarify()
    result = await agents[Stage.CLARIFY].run(session, requirement=requirement)
    console.print(f"  {'✅' if result.success else '❌'} {result.message}")
    session_manager.save(session)

    if not result.success:
        console.print("[red]Requirement clarification failed. Aborting.[/red]")
        return

    # 人工检查点
    cp_result = await checkpoint_gate.check(session, Stage.CLARIFY, result.output)
    if cp_result.get("_checkpoint_action") == "redo":
        console.print("[yellow]User requested redo.[/yellow]")
        return

    # ===== STAGE 2: PLAN =====
    console.print("\n[bold blue]▶ Stage: PLAN[/bold blue]")
    if sm.start_plan():
        max_plan_attempts = 3
        for attempt in range(max_plan_attempts):
            result = await agents[Stage.PLAN].run(session)
            console.print(f"  {'✅' if result.success else '❌'} {result.message}")

            if result.success:
                # 自检
                check = await self_check.check_stage(session, Stage.PLAN, result.output)
                console.print(f"  [dim]Self-check: {check.message}[/dim]")
                if check.success:
                    break
                else:
                    console.print(f"  [yellow]Retrying plan (attempt {attempt + 2}/{max_plan_attempts})...[/yellow]")
            else:
                if attempt < max_plan_attempts - 1:
                    console.print(f"  [yellow]Retrying plan (attempt {attempt + 2}/{max_plan_attempts})...[/yellow]")
                else:
                    console.print("[red]Planning failed after max attempts.[/red]")
                    return

        session_manager.save(session)
        cp_result = await checkpoint_gate.check(session, Stage.PLAN, result.output)
        if cp_result.get("_checkpoint_action") == "redo":
            return
        if cp_result.get("_checkpoint_action") == "backtrack":
            return
    else:
        console.print("[red]Cannot enter PLAN stage (requirements not ready).[/red]")
        return

    # ===== STAGE 3: LOCATE =====
    console.print("\n[bold blue]▶ Stage: LOCATE[/bold blue]")
    if sm.start_locate():
        result = await agents[Stage.LOCATE].run(session)
        console.print(f"  {'✅' if result.success else '❌'} {result.message}")
        session_manager.save(session)

        if not result.success:
            console.print("[red]Module location failed. Aborting.[/red]")
            return

        cp_result = await checkpoint_gate.check(session, Stage.LOCATE, result.output)
        if cp_result.get("_checkpoint_action") == "redo":
            return
    else:
        console.print("[red]Cannot enter LOCATE stage (plan tasks not completed).[/red]")
        return

    # ===== STAGE 4: CODE =====
    console.print("\n[bold blue]▶ Stage: CODE[/bold blue]")
    if sm.start_code():
        max_code_attempts = 3
        for attempt in range(max_code_attempts):
            result = await agents[Stage.CODE].run(session)
            console.print(f"  {'✅' if result.success else '❌'} {result.message}")

            if result.success:
                check = await self_check.check_stage(session, Stage.CODE, result.output)
                console.print(f"  [dim]Self-check: {check.message}[/dim]")
                if check.success:
                    break
                else:
                    console.print(f"  [yellow]Retrying code (attempt {attempt + 2}/{max_code_attempts})...[/yellow]")
            else:
                if result.should_retry and attempt < max_code_attempts - 1:
                    console.print(f"  [yellow]Retrying code (attempt {attempt + 2}/{max_code_attempts})...[/yellow]")
                else:
                    console.print("[red]Coding failed after max attempts.[/red]")
                    return

        session_manager.save(session)
        cp_result = await checkpoint_gate.check(session, Stage.CODE, result.output)
        if cp_result.get("_checkpoint_action") == "redo":
            return
    else:
        console.print("[red]Cannot enter CODE stage (locate tasks not completed).[/red]")
        return

    # ===== STAGE 5: TEST =====
    console.print("\n[bold blue]▶ Stage: TEST[/bold blue]")
    if sm.start_test():
        max_test_attempts = 3
        for attempt in range(max_test_attempts):
            result = await agents[Stage.TEST].run(session)
            console.print(f"  {'✅' if result.success else '❌'} {result.message}")

            if result.success:
                break
            else:
                if result.should_retry and attempt < max_test_attempts - 1:
                    console.print(f"  [yellow]Retrying tests (attempt {attempt + 2}/{max_test_attempts})...[/yellow]")
                else:
                    console.print("[red]Testing failed after max attempts.[/red]")
                    return

        session_manager.save(session)
        cp_result = await checkpoint_gate.check(session, Stage.TEST, result.output)
        if cp_result.get("_checkpoint_action") == "redo":
            return
    else:
        console.print("[red]Cannot enter TEST stage (code tasks not completed).[/red]")
        return

    # ===== STAGE 6: DEPLOY =====
    console.print("\n[bold blue]▶ Stage: DEPLOY[/bold blue]")
    if sm.start_deploy():
        result = await agents[Stage.DEPLOY].run(session)
        console.print(f"  {'✅' if result.success else '❌'} {result.message}")
        session_manager.save(session)

        if result.success:
            sm.finish()
            console.print(Panel(
                f"[bold green]🎉 GoalFlow Workflow Complete![/bold green]\n"
                f"Session: {session.id}\n"
                f"PR: {result.output.get('pr_url', 'N/A')}",
                title="Done",
            ))
        else:
            console.print(Panel(
                f"[yellow]⚠️ Deploy stage completed with warnings[/yellow]\n"
                f"{result.message}\n"
                f"Branch: {result.output.get('branch', 'N/A')}",
                title="Deploy",
            ))
    else:
        console.print("[red]Cannot enter DEPLOY stage (test tasks not completed).[/red]")
        return


@click.group()
def main():
    """GoalFlow — 目标锚定的全链路智能开发平台."""
    pass


@main.command()
@click.argument("repo_path")
@click.argument("requirement")
@click.option("--auto/--manual", default=True, help="Auto mode (skip checkpoints) or manual mode.")
@click.option("--github-token", envvar="GITHUB_TOKEN", help="GitHub personal access token.")
@click.option("--model", envvar="GOALFLOW_MODEL", default="gpt-4o", help="LLM model.")
def run(repo_path: str, requirement: str, auto: bool, github_token: Optional[str], model: str):
    """运行完整工作流.

    REPO_PATH: 本地代码库路径\n
    REQUIREMENT: 自然语言需求描述（或用 @file.txt 从文件读取）
    """
    if requirement.startswith("@"):
        req_file = Path(requirement[1:])
        if req_file.exists():
            requirement = req_file.read_text(encoding="utf-8")
        else:
            console.print(f"[red]Requirement file not found: {req_file}[/red]")
            return

    repo_path = str(Path(repo_path).resolve())
    if not Path(repo_path).exists():
        console.print(f"[red]Repo path not found: {repo_path}[/red]")
        return

    # 设置环境变量
    if model:
        os.environ["GOALFLOW_MODEL"] = model

    session = Session(repo_path=repo_path, github_token=github_token)
    event_bus = EventBus()
    session_manager = SessionManager()
    checkpoint_gate = CheckpointGate()

    asyncio.run(run_workflow(
        session=session,
        requirement=requirement,
        event_bus=event_bus,
        session_manager=session_manager,
        checkpoint_gate=checkpoint_gate,
        auto_mode=auto,
    ))


@main.command()
def list():
    """列出所有 Session."""
    session_manager = SessionManager()
    sessions = session_manager.list_sessions()

    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Updated At", style="dim")

    for s in sessions:
        table.add_row(s["id"], s["updated_at"])

    console.print(table)


@main.command()
@click.argument("session_id")
def resume(session_id: str):
    """恢复指定 Session（TODO: 实现断点续跑）."""
    console.print(f"[yellow]Resume not yet implemented. Session: {session_id}[/yellow]")


@main.command()
@click.argument("session_id")
def show(session_id: str):
    """查看 Session 详情."""
    session_manager = SessionManager()
    session = session_manager.load(session_id)
    if not session:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    console.print(Panel(
        f"[bold]Session: {session.id}[/bold]\n"
        f"Repo: {session.repo_path}\n"
        f"Stage: {session.current_stage.value}\n"
        f"Tasks: {len(session.tasks)} total, "
        f"{len([t for t in session.tasks if t.status.value == 'completed'])} completed\n"
        f"Created: {session.created_at}",
        title="Session Detail",
    ))


if __name__ == "__main__":
    main()
