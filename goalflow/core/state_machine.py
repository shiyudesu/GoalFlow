"""工作流状态机 — 驱动6阶段流转，含防漂移约束."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from transitions import Machine

from .models import Event, EventType, Session, Stage, TaskStatus


class WorkflowStateMachine:
    """GoalFlow 工作流状态机.

    核心约束：
    1. 前一阶段原子任务未全部完成，禁止向前流转。
    2. 每个阶段完成后触发一致性校验（除 INIT/DONE）。
    3. 支持人工检查点暂停。
    """

    STAGES = [
        Stage.INIT,
        Stage.CLARIFY,
        Stage.PLAN,
        Stage.LOCATE,
        Stage.CODE,
        Stage.TEST,
        Stage.DEPLOY,
        Stage.DONE,
    ]

    def __init__(
        self,
        session: Session,
        on_transition: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        self.session = session
        self.on_transition = on_transition
        self._machine = Machine(
            model=self,
            states=[s.value for s in self.STAGES],
            initial=Stage.INIT.value,
            send_event=True,
        )
        self._setup_transitions()

    def _setup_transitions(self) -> None:
        """配置状态转换."""
        transitions = [
            {"trigger": "start_clarify", "source": Stage.INIT.value, "dest": Stage.CLARIFY.value},
            {"trigger": "start_plan", "source": Stage.CLARIFY.value, "dest": Stage.PLAN.value, "conditions": "_can_leave_clarify"},
            {"trigger": "start_locate", "source": Stage.PLAN.value, "dest": Stage.LOCATE.value, "conditions": "_can_leave_plan"},
            {"trigger": "start_code", "source": Stage.LOCATE.value, "dest": Stage.CODE.value, "conditions": "_can_leave_locate"},
            {"trigger": "start_test", "source": Stage.CODE.value, "dest": Stage.TEST.value, "conditions": "_can_leave_code"},
            {"trigger": "start_deploy", "source": Stage.TEST.value, "dest": Stage.DEPLOY.value, "conditions": "_can_leave_test"},
            {"trigger": "finish", "source": Stage.DEPLOY.value, "dest": Stage.DONE.value, "conditions": "_can_leave_deploy"},
            # 支持回退
            {"trigger": "backtrack", "source": "*", "dest": Stage.PLAN.value},
        ]
        for t in transitions:
            self._machine.add_transition(**t)

    # ========== 阶段离开条件（防漂移核心）==========

    def _can_leave_clarify(self, event) -> bool:
        """离开 CLARIFY：必须有 PRD."""
        return self.session.prd is not None

    def _can_leave_plan(self, event) -> bool:
        """离开 PLAN：所有 PLAN 阶段任务必须完成."""
        return self.session.all_tasks_completed(Stage.PLAN)

    def _can_leave_locate(self, event) -> bool:
        """离开 LOCATE：所有 LOCATE 阶段任务必须完成."""
        return self.session.all_tasks_completed(Stage.LOCATE)

    def _can_leave_code(self, event) -> bool:
        """离开 CODE：所有 CODE 阶段任务必须完成."""
        return self.session.all_tasks_completed(Stage.CODE)

    def _can_leave_test(self, event) -> bool:
        """离开 TEST：所有 TEST 阶段任务必须完成."""
        return self.session.all_tasks_completed(Stage.TEST)

    def _can_leave_deploy(self, event) -> bool:
        """离开 DEPLOY：PR 已合并或达到最大重试."""
        deploy_output = self.session.stage_outputs.get(Stage.DEPLOY, {})
        return deploy_output.get("pr_merged", False) or deploy_output.get("max_retries_reached", False)

    # ========== 状态变更回调 ==========

    def on_enter_clarify(self, event):
        self.session.current_stage = Stage.CLARIFY

    def on_enter_plan(self, event):
        self.session.current_stage = Stage.PLAN

    def on_enter_locate(self, event):
        self.session.current_stage = Stage.LOCATE

    def on_enter_code(self, event):
        self.session.current_stage = Stage.CODE

    def on_enter_test(self, event):
        self.session.current_stage = Stage.TEST

    def on_enter_deploy(self, event):
        self.session.current_stage = Stage.DEPLOY

    def on_enter_done(self, event):
        self.session.current_stage = Stage.DONE

    def after_state_change(self, event):
        """状态变更后回调."""
        if self.on_transition:
            src = event.transition.source if hasattr(event, "transition") else ""
            dst = event.transition.dest if hasattr(event, "transition") else ""
            self.on_transition(src, dst)

    @property
    def current_stage(self) -> Stage:
        return Stage(self.state)
