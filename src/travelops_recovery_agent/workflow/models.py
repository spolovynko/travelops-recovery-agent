"""Strict durable-workflow identities, lifecycle values, and safe events."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=96),
]
SafePayload = dict[str, JsonValue]


class WorkflowContract(BaseModel):
    """Frozen strict base for durable workflow values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkflowStatus(StrEnum):
    """Application-owned lifecycle surrounding one LangGraph thread."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    AWAITING_INFORMATION = "awaiting_information"
    FAILED = "failed"

    @property
    def is_active(self) -> bool:
        return self in {
            WorkflowStatus.CREATED,
            WorkflowStatus.RUNNING,
            WorkflowStatus.PAUSED,
            WorkflowStatus.CANCELLING,
        }

    @property
    def is_terminal(self) -> bool:
        return self in {
            WorkflowStatus.CANCELLED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.AWAITING_INFORMATION,
            WorkflowStatus.FAILED,
        }


class WorkflowEventType(StrEnum):
    """Versioned operator-visible activity without hidden reasoning."""

    RUN_CREATED = "workflow.created"
    RUN_STARTED = "workflow.started"
    RUN_RESUMED = "workflow.resumed"
    RUN_PAUSED = "workflow.paused"
    CANCELLATION_REQUESTED = "workflow.cancellation_requested"
    RUN_CANCELLED = "workflow.cancelled"
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    EVIDENCE_RECORDED = "evidence.recorded"
    RETRY_SCHEDULED = "workflow.retry_scheduled"
    RUN_COMPLETED = "workflow.completed"
    RUN_AWAITING_INFORMATION = "workflow.awaiting_information"
    RUN_FAILED = "workflow.failed"
    REPLAY_RESET_REQUIRED = "stream.replay_reset_required"
    RECOMMENDATION_COMPLETED = "recommendation.completed"
    RECOMMENDATION_ESCALATED = "recommendation.escalated"


class WorkflowIdentity(WorkflowContract):
    """Stable relationship among one case, workflow run, and graph thread."""

    case_id: Identifier
    run_id: Identifier
    thread_id: Identifier


def new_workflow_identity(case_id: str) -> WorkflowIdentity:
    """Create distinct opaque identifiers for one new case investigation."""

    return WorkflowIdentity(
        case_id=case_id,
        run_id=f"run-{uuid4().hex}",
        thread_id=f"thread-{uuid4().hex}",
    )


class WorkflowRun(WorkflowContract):
    """Application lifecycle metadata, separate from graph checkpoints."""

    identity: WorkflowIdentity
    status: WorkflowStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    paused_at: datetime | None = None
    lease_owner: Identifier | None = None
    lease_expires_at: datetime | None = None
    last_event_sequence: Annotated[int, Field(ge=0)] = 0
    version: Annotated[int, Field(ge=1)] = 1
    failure_code: Identifier | None = None

    @field_validator(
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "cancel_requested_at",
        "paused_at",
        "lease_expires_at",
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("workflow timestamps must be timezone-aware")
        return value


_FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "arguments",
        "chain_of_thought",
        "credential",
        "credentials",
        "exception",
        "passenger",
        "passengers",
        "prompt",
        "raw",
        "sql",
        "traceback",
    }
)


def _validate_safe_payload(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.casefold()
            if normalized in _FORBIDDEN_EVENT_KEYS:
                location = ".".join((*path, key))
                raise ValueError(f"unsafe workflow event field: {location}")
            _validate_safe_payload(item, (*path, key))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _validate_safe_payload(item, (*path, str(index)))


class WorkflowEvent(WorkflowContract):
    """One ordered safe event suitable for persistence and SSE delivery."""

    event_id: Identifier
    run_id: Identifier
    sequence: Annotated[int, Field(gt=0)]
    type: WorkflowEventType
    occurred_at: datetime
    payload: SafePayload = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_event_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value

    @field_validator("payload")
    @classmethod
    def reject_sensitive_fields(cls, value: SafePayload) -> SafePayload:
        _validate_safe_payload(value)
        return value

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        sequence: int,
        type: WorkflowEventType,
        occurred_at: datetime,
        payload: SafePayload | None = None,
    ) -> Self:
        return cls(
            event_id=f"{run_id}:{sequence}",
            run_id=run_id,
            sequence=sequence,
            type=type,
            occurred_at=occurred_at,
            payload=payload or {},
        )
