"""GitHub 客户端 — PR 生命周期管理."""

from __future__ import annotations

from typing import Any, List, Optional

from github import Github
from github.PullRequest import PullRequest


class GitHubClient:
    """GitHub API 封装.

    提供 PR 创建、状态查询、Review 监控、合并等操作。
    """

    def __init__(self, token: str) -> None:
        self.g = Github(token)

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> PullRequest:
        """创建 PR."""
        repository = self.g.get_repo(f"{owner}/{repo}")
        pr = repository.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft,
        )
        return pr

    def get_pull_request(self, owner: str, repo: str, number: int) -> PullRequest:
        """获取 PR."""
        repository = self.g.get_repo(f"{owner}/{repo}")
        return repository.get_pull(number)

    def list_reviews(self, pr: PullRequest) -> List[Any]:
        """获取 PR 的 Reviews."""
        return list(pr.get_reviews())

    def get_review_comments(self, pr: PullRequest) -> List[Any]:
        """获取 PR Review Comments."""
        return list(pr.get_review_comments())

    def request_reviewers(self, pr: PullRequest, reviewers: List[str]) -> None:
        """请求 Reviewer."""
        pr.create_review_request(reviewers=reviewers)

    def merge_pull_request(
        self,
        pr: PullRequest,
        commit_message: Optional[str] = None,
    ) -> bool:
        """合并 PR."""
        try:
            pr.merge(commit_message=commit_message or pr.title)
            return True
        except Exception:
            return False

    def get_ci_status(self, pr: PullRequest) -> str:
        """获取 CI 状态."""
        # 获取最新 commit 的状态
        commits = list(pr.get_commits())
        if not commits:
            return "unknown"
        latest = commits[-1]
        statuses = latest.get_statuses()
        if not statuses:
            # 尝试检查 checks
            check_runs = latest.get_check_runs()
            if not check_runs:
                return "pending"
            # 汇总 check 状态
            states = [cr.conclusion for cr in check_runs]
            if any(s == "failure" for s in states):
                return "failure"
            if all(s == "success" for s in states):
                return "success"
            return "pending"

        # 使用 status API
        latest_status = statuses[0]
        return latest_status.state
