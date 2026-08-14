"""Privacy-safe Phase 11 trace events with stable schema versioning."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

TRACE_SCHEMA_VERSION = "travelops.trace.v1"
_SENSITIVE_KEYS = re.compile(
    r"(authorization|cookie|credential|password|secret|token|passenger|prompt|idempotency)",
    re.IGNORECASE,
)


class TraceKind(StrEnum):
    API_REQUEST = "api_request"
    WORKFLOW_NODE = "workflow_node"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    RETRY = "retry"
    INTERRUPT = "interrupt"
    TERMINAL_OUTCOME = "terminal_outcome"
    EVALUATION_CASE = "evaluation_case"


def safe_reference(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def redact_metadata(value: Any) -> Any:
    """Recursively retain bounded primitives while removing unsafe keys/content."""

    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:50]:
            key = str(raw_key)[:64]
            if _SENSITIVE_KEYS.search(key):
                clean[key] = "[REDACTED]"
            else:
                clean[key] = redact_metadata(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [redact_metadata(item) for item in list(value)[:50]]
    if isinstance(value, str):
        return value[:500].replace("\r", " ").replace("\n", " ")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = TRACE_SCHEMA_VERSION
    trace_id: str = Field(min_length=1, max_length=128)
    span_id: str = Field(min_length=1, max_length=128)
    parent_span_id: str | None = Field(default=None, max_length=128)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: TraceKind
    name: str = Field(min_length=1, max_length=100)
    status: str = Field(pattern=r"^(started|succeeded|failed|interrupted)$")
    duration_ms: float | None = Field(default=None, ge=0)
    request_id: str | None = Field(default=None, max_length=128)
    workflow_run_id: str | None = Field(default=None, max_length=128)
    case_reference: str | None = Field(default=None, max_length=128)
    proposal_reference: str | None = Field(default=None, max_length=128)
    evaluation_case_id: str | None = Field(default=None, max_length=128)
    error_category: str | None = Field(default=None, max_length=64)
    retry_count: int = Field(default=0, ge=0, le=20)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    cost_source: str | None = Field(
        default=None, pattern=r"^(measured|reported|estimated)$"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def sanitize_metadata(cls, value: Any) -> dict[str, Any]:
        sanitized = redact_metadata(value)
        return sanitized if isinstance(sanitized, dict) else {}

    @field_validator("cost_source")
    @classmethod
    def require_cost_for_source(cls, value: str | None, info: Any) -> str | None:
        if value is not None and info.data.get("cost_usd") is None:
            raise ValueError("cost_source requires cost_usd")
        return value


def export_jsonl(events: list[TraceEvent], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(event.model_dump_json() for event in events)
    path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")


def inspect_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
