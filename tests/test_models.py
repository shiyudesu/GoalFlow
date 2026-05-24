"""测试核心数据模型."""

import pytest
from goalflow.core.models import PRD, Session, Stage, Task, TaskStatus


class TestPRD:
    def test_to_anchor_text(self):
        prd = PRD(
            raw_requirement="add user auth",
            clarified_requirement="Add JWT-based user authentication",
            functional_requirements=["login", "register", "logout"],
            non_functional_requirements=["secure", "fast"],
            constraints=["use existing DB"],
        )
        text = prd.to_anchor_text()
        assert "JWT-based user authentication" in text
        assert "login" in text
        assert "secure" in text


class TestSession:
    def test_all_tasks_completed(self):
        session = Session(repo_path="/tmp/test")
        session.tasks = [
            Task(title="t1", stage=Stage.CODE, status=TaskStatus.COMPLETED),
            Task(title="t2", stage=Stage.CODE, status=TaskStatus.COMPLETED),
            Task(title="t3", stage=Stage.TEST, status=TaskStatus.PENDING),
        ]
        assert session.all_tasks_completed(Stage.CODE) is True
        assert session.all_tasks_completed(Stage.TEST) is False

    def test_get_pending_tasks(self):
        session = Session(repo_path="/tmp/test")
        session.tasks = [
            Task(title="t1", stage=Stage.CODE, status=TaskStatus.COMPLETED),
            Task(title="t2", stage=Stage.CODE, status=TaskStatus.PENDING),
        ]
        pending = session.get_pending_tasks(Stage.CODE)
        assert len(pending) == 1
        assert pending[0].title == "t2"


class TestTask:
    def test_can_retry(self):
        task = Task(title="t", max_attempts=3)
        assert task.can_retry() is True
        task.attempts = 3
        assert task.can_retry() is False

    def test_mark_attempt(self):
        task = Task(title="t")
        task.mark_attempt()
        assert task.attempts == 1
