"""测试状态机."""

import pytest
from goalflow.core.models import PRD, Session, Stage, Task, TaskStatus
from goalflow.core.state_machine import WorkflowStateMachine


class TestWorkflowStateMachine:
    def test_init(self):
        session = Session(repo_path="/tmp/test")
        sm = WorkflowStateMachine(session)
        assert sm.current_stage == Stage.INIT

    def test_can_leave_clarify_without_prd(self):
        session = Session(repo_path="/tmp/test")
        sm = WorkflowStateMachine(session)
        sm.start_clarify()
        # PRD is None, should not be able to leave
        result = sm._can_leave_clarify(None)
        assert result is False

    def test_can_leave_clarify_with_prd(self):
        session = Session(repo_path="/tmp/test")
        session.prd = PRD(raw_requirement="test")
        sm = WorkflowStateMachine(session)
        sm.start_clarify()
        result = sm._can_leave_clarify(None)
        assert result is True

    def test_can_leave_plan_with_incomplete_tasks(self):
        session = Session(repo_path="/tmp/test")
        session.prd = PRD(raw_requirement="test")
        session.tasks = [
            Task(title="t1", stage=Stage.PLAN, status=TaskStatus.PENDING),
        ]
        sm = WorkflowStateMachine(session)
        sm.start_clarify()
        sm.start_plan()
        result = sm._can_leave_plan(None)
        assert result is False

    def test_can_leave_plan_with_complete_tasks(self):
        session = Session(repo_path="/tmp/test")
        session.prd = PRD(raw_requirement="test")
        session.tasks = [
            Task(title="t1", stage=Stage.PLAN, status=TaskStatus.COMPLETED),
        ]
        sm = WorkflowStateMachine(session)
        sm.start_clarify()
        sm.start_plan()
        result = sm._can_leave_plan(None)
        assert result is True

    def test_full_flow(self):
        session = Session(repo_path="/tmp/test")
        session.prd = PRD(raw_requirement="test")
        session.tasks = [
            Task(title="t1", stage=Stage.PLAN, status=TaskStatus.COMPLETED),
            Task(title="t2", stage=Stage.LOCATE, status=TaskStatus.COMPLETED),
            Task(title="t3", stage=Stage.CODE, status=TaskStatus.COMPLETED),
            Task(title="t4", stage=Stage.TEST, status=TaskStatus.COMPLETED),
        ]
        session.stage_outputs[Stage.DEPLOY] = {"pr_merged": True}

        sm = WorkflowStateMachine(session)
        assert sm.start_clarify() is True
        assert sm.start_plan() is True
        assert sm.start_locate() is True
        assert sm.start_code() is True
        assert sm.start_test() is True
        assert sm.start_deploy() is True
        assert sm.finish() is True
        assert session.current_stage == Stage.DONE
