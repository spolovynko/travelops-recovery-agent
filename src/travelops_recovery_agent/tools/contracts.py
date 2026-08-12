"""Shared contracts for read-only operational tools."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class ToolContractModel(BaseModel):
    """Strict immutable base for every tool-boundary model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolPermission(StrEnum):
    """Explicit permissions granted to a tool caller."""

    READ_BOOKING = "booking:read"
    READ_FLIGHT_STATUS = "flight_status:read"
    READ_DISRUPTION_POLICY = "disruption_policy:read"
    SEARCH_ALTERNATIVE_ITINERARIES = "alternative_itineraries:search"
    VALIDATE_ITINERARY = "itinerary:validate"


class ToolErrorCode(StrEnum):
    """Safe, stable categories for tool failures."""

    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    DEPENDENCY_FAILURE = "dependency_failure"


class ToolAuditOutcome(StrEnum):
    """Possible audited outcomes of a tool call."""

    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


class ToolExecutionContext(ToolContractModel):
    """Caller identity, permissions, correlation, and deadline for one call."""

    actor_id: NonEmptyText
    correlation_id: NonEmptyText
    permissions: frozenset[ToolPermission]
    deadline_at: datetime

    @field_validator("deadline_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline_at must be timezone-aware")
        return value


class ToolAuditMetadata(ToolContractModel):
    """Safe operational facts recorded about one tool execution."""

    tool_name: NonEmptyText
    actor_id: NonEmptyText
    correlation_id: NonEmptyText
    required_permission: ToolPermission
    outcome: ToolAuditOutcome
    started_at: datetime
    completed_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("audit timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timing(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


class ToolError(ToolContractModel):
    """Structured failure safe to expose outside the application."""

    code: ToolErrorCode
    message: NonEmptyText
    retryable: bool


class ToolSuccess[OutputT: BaseModel](ToolContractModel):
    """Successful tool result containing typed output and audit metadata."""

    ok: Literal[True] = True
    result: OutputT
    audit: ToolAuditMetadata


class ToolFailure(ToolContractModel):
    """Failed tool result containing a safe error and audit metadata."""

    ok: Literal[False] = False
    error: ToolError
    audit: ToolAuditMetadata


type ToolResult[OutputT: BaseModel] = ToolSuccess[OutputT] | ToolFailure
