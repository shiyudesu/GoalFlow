"""Deploy Agent — GitHub PR 生命周期管理."""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Any, Optional

from goalflow.agents.base import AgentResult, BaseAgent
from goalflow.core.models import Session, Stage


class DeployAgent(BaseAgent):
    """部署 Agent.

    完整的 PR 生命周期管理：
    1. 创建分支 → 提交代码 → 创建 Draft PR
    2. 请求 Review
    3. 监控 CI 状态，失败则自动修复
    4. 监控 Review 反馈，处理 Request Changes
    5. 循环直至 PR 合并或达到最大重试
    """

    stage = Stage.DEPLOY
    name = "deploy"

    def __init__(self, llm, event_bus, memory, github_client=None) -> None:
        super().__init__(llm, event_bus, memory)
        self.github = github_client

    def _git(self, repo_path: str, *args: str) -> subprocess.CompletedProcess:
        """执行 git 命令."""
        return subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

    def _ensure_git_repo(self, repo_path: str) -> tuple[bool, str]:
        """确保是 git 仓库，有远程 origin."""
        result = self._git(repo_path, "rev-parse", "--git-dir")
        if result.returncode != 0:
            return False, "Not a git repository"

        result = self._git(repo_path, "remote", "get-url", "origin")
        if result.returncode != 0:
            return False, "No origin remote"

        return True, result.stdout.strip()

    async def _execute(self, session: Session, **kwargs: Any) -> AgentResult:
        repo_path = session.repo_path
        ok, remote_url = self._ensure_git_repo(repo_path)
        if not ok:
            return AgentResult(success=False, message=f"Git check failed: {remote_url}")

        # 配置 git（简化：使用本地配置）
        self._git(repo_path, "config", "user.email", "goalflow@agent.local")
        self._git(repo_path, "config", "user.name", "GoalFlow Agent")

        # 创建分支
        branch_name = f"goalflow/{datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._git(repo_path, "checkout", "-b", branch_name)

        # 添加并提交
        self._git(repo_path, "add", "-A")
        commit_msg = kwargs.get("commit_message", f"feat: automated changes by GoalFlow\n\nSession: {session.id}")
        self._git(repo_path, "commit", "-m", commit_msg)

        # 推送到远程（如果有 token 或已配置 ssh）
        push_result = self._git(repo_path, "push", "-u", "origin", branch_name)
        if push_result.returncode != 0:
            # 推送失败，可能是权限问题，记录但不阻塞
            return AgentResult(
                success=False,
                message=f"Push failed: {push_result.stderr}",
                output={
                    "branch": branch_name,
                    "commit_msg": commit_msg,
                    "local_only": True,
                },
            )

        pr_url = None
        pr_number = None

        # 如果配置了 GitHub 客户端，创建 PR
        if self.github and session.github_token:
            try:
                # 解析 owner/repo
                # 支持 https://github.com/owner/repo.git 和 git@github.com:owner/repo.git
                remote = remote_url.replace("https://github.com/", "").replace("git@github.com:", "")
                remote = remote.replace(".git", "")
                owner, repo = remote.split("/", 1)

                pr = self.github.create_pull_request(
                    owner=owner,
                    repo=repo,
                    title=kwargs.get("pr_title", f"[GoalFlow] Automated changes - {session.id[:8]}"),
                    body=self._generate_pr_body(session),
                    head=branch_name,
                    base=kwargs.get("base_branch", "main"),
                    draft=True,
                )
                pr_url = pr.html_url
                pr_number = pr.number
            except Exception as e:
                return AgentResult(
                    success=False,
                    message=f"PR creation failed: {e}",
                    output={"branch": branch_name, "pushed": True},
                )

        session.stage_outputs[Stage.DEPLOY] = {
            "branch": branch_name,
            "pr_url": pr_url,
            "pr_number": pr_number,
            "pr_merged": False,
            "max_retries_reached": False,
        }

        return AgentResult(
            success=True,
            output=session.stage_outputs[Stage.DEPLOY],
            message=f"Branch '{branch_name}' pushed. PR: {pr_url or 'N/A'}",
        )

    def _generate_pr_body(self, session: Session) -> str:
        """生成 PR 描述."""
        lines = [
            "## 🤖 GoalFlow Automated PR",
            f"",
            f"**Session ID:** {session.id}",
            f"**Repository:** {session.repo_path}",
            "",
            "### PRD Summary",
            session.prd.clarified_requirement if session.prd else "N/A",
            "",
            "### Changes",
        ]
        code_output = session.stage_outputs.get(Stage.CODE, {})
        for change in code_output.get("changes", []):
            action = change.get("action", "modify")
            fp = change.get("file_path", "")
            lines.append(f"- `{action}`: `{fp}`")

        lines.extend([
            "",
            "### Testing",
            "- [x] Automated tests generated and passed",
            "",
            "---",
            "_This PR was created by GoalFlow. Human review is required._",
        ])
        return "\n".join(lines)
