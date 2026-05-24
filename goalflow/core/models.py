"""核心数据模型."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Stage(str, enum.Enum):
    """工作流阶段."""

    INIT = "init"
    CLARIFY = "clarify"
    PLAN = "plan"
    LOCATE = "locate"
    CODE = "code"
    TEST = "test"
    DEPLOY = "deploy"
    DONE = "done"


class EventType(str, enum.Enum):
    """事件类型."""

    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    STAGE_HUMAN_INTERVENTION = "stage.human_intervention"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    PR_CREATED = "pr.created"
    PR_REVIEW_RECEIVED = "pr.review_received"
    PR_CI_STATUS_CHANGED = "pr.ci_status_changed"
    CONSISTENCY_CHECK_FAILED = "consistency_check.failed"
    ESCALATION = "escalation"


class TaskStatus(str, enum.Enum):
    """任务状态."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class Task(BaseModel):
    """原子任务."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    dod: str = ""  # Definition of Done
    status: TaskStatus = TaskStatus.PENDING
    stage: Stage = Stage.PLAN
    attempts: int = 0
    max_attempts: int = 5
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))

    def can_retry(self) -> bool:
        """检查是否还可以重试."""
        return self.attempts < self.max_attempts

    def mark_attempt(self) -> None:
        """标记一次尝试."""
        self.attempts += 1
        self.updated_at = datetime.now(tz=__import__("datetime").timezone.utc)


class PRD(BaseModel):
    """需求文档（不可变锚点）."""

    raw_requirement: str
    clarified_requirement: str = ""
    functional_requirements: List[str] = Field(default_factory=list)
    non_functional_requirements: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))

    def to_anchor_text(self) -> str:
        """生成锚点文本，用于一致性校验."""
        parts = [
            "=== PRD Anchor ===",
            f"Clarified: {self.clarified_requirement}",
            "Functional:",
            *[f"  - {r}" for r in self.functional_requirements],
            "Non-functional:",
            *[f"  - {r}" for r in self.non_functional_requirements],
            "Constraints:",
            *[f"  - {c}" for c in self.constraints],
            "=== End Anchor ===",
        ]
        return "\n".join(parts)


class Session(BaseModel):
    """工作会话."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_path: str
    repo_url: Optional[str] = None
    github_token: Optional[str] = None
    current_stage: Stage = Stage.INIT
    prd: Optional[PRD] = None
    tasks: List[Task] = Field(default_factory=list)
    stage_outputs: Dict[Stage, Dict[str, Any]] = Field(default_factory=dict)
    checkpoint_config: Dict[Stage, str] = Field(
        default_factory=lambda: {stage: "auto" for stage in Stage}
    )
    context_summary: str = ""  # 分层摘要，防止上下文丢失
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))

    def get_pending_tasks(self, stage: Optional[Stage] = None) -> List[Task]:
        """获取未完成的任务."""
        tasks = [t for t in self.tasks if t.status != TaskStatus.COMPLETED]
        if stage:
            tasks = [t for t in tasks if t.stage == stage]
        return tasks

    def all_tasks_completed(self, stage: Stage) -> bool:
        """检查某阶段所有任务是否已完成."""
        stage_tasks = [t for t in self.tasks if t.stage == stage]
        if not stage_tasks:
            return False
        return all(t.status == TaskStatus.COMPLETED for t in stage_tasks)

    def update_summary(self, new_content: str) -> None:
        """更新上下文摘要."""
        self.context_summary = new_content
        self.updated_at = datetime.now(tz=__import__("datetime").timezone.utc)


class Event(BaseModel):
    """事件."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    type: EventType
    stage: Optional[Stage] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))
