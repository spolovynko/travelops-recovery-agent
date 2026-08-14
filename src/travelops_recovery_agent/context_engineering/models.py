"""Strict provider-neutral contracts for Phase 12 model context."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

CONTEXT_SCHEMA_VERSION: Literal["travelops.context.v1"] = "travelops.context.v1"
CONTEXT_POLICY_VERSION: Literal["phase-12.1"] = "phase-12.1"
CONTEXT_CACHE_VERSION: Literal["phase-12.1"] = "phase-12.1"
TOKEN_ESTIMATE_METHOD: Literal["estimated_characters_div_4"] = (
    "estimated_characters_div_4"
)

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=12_000),
]


class ContextContract(BaseModel):
    """Strict immutable base for context-boundary data."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ContextTask(StrEnum):
    INTAKE = "intake"
    INVESTIGATE = "investigate"
    RECOMMEND = "recommend"
    PREPARE_PROPOSAL = "prepare_proposal"
    REVIEW_APPROVAL = "review_approval"
    EXECUTE_REBOOKING = "execute_rebooking"


class ContextSourceType(StrEnum):
    BUSINESS_FACT = "business_fact"
    OPERATIONAL_EVIDENCE = "operational_evidence"
    POLICY = "policy"
    TOOL_RESULT = "tool_result"
    OPERATOR_INSTRUCTION = "operator_instruction"
    CONVERSATION_TURN = "conversation_turn"
    CONVERSATION_SUMMARY = "conversation_summary"
    APPROVAL = "approval"
    EXECUTION_EVIDENCE = "execution_evidence"


class AuthorityLevel(IntEnum):
    UNTRUSTED = 0
    DERIVED = 1
    OPERATOR = 2
    APPLICATION = 3
    AUTHORITATIVE = 4


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    RESTRICTED = "restricted"
    SECRET = "secret"


class FreshnessState(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class SelectionDisposition(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    COMPACTED = "compacted"
    REJECTED = "rejected"


class SelectionReason(StrEnum):
    MANDATORY = "mandatory_evidence"
    RELEVANT = "relevant_current_evidence"
    COMPACTED_TO_FIT = "compacted_to_fit_budget"
    TASK_MISMATCH = "task_mismatch"
    NODE_MISMATCH = "workflow_node_mismatch"
    LOW_RELEVANCE = "low_relevance"
    STALE = "stale_evidence"
    EXPIRED = "expired_evidence"
    UNKNOWN_FRESHNESS = "unknown_freshness"
    UNAUTHORIZED = "unauthorized_evidence"
    CROSS_CASE = "cross_case_evidence"
    SENSITIVITY = "sensitivity_not_permitted"
    SECRET = "secret_never_model_visible"
    UNTRUSTED = "untrusted_evidence"
    SUPERSEDED = "superseded_evidence"
    CONFLICT = "conflict_lower_authority"
    BUDGET = "context_budget_exhausted"
    MANDATORY_MISSING = "mandatory_evidence_missing"
    MANDATORY_TOO_LARGE = "mandatory_evidence_exceeds_budget"


class BuildStatus(StrEnum):
    READY = "ready"
    ESCALATED = "safe_escalation"


class TokenAccounting(ContextContract):
    budget: Annotated[int, Field(ge=1, le=100_000)]
    selected_estimate: Annotated[int, Field(ge=0)]
    tool_schema_estimate: Annotated[int, Field(ge=0)]
    remaining_estimate: Annotated[int, Field(ge=0)]
    estimate_method: Literal["estimated_characters_div_4"] = TOKEN_ESTIMATE_METHOD
    provider_exact: Literal[False] = False


class ContextItem(ContextContract):
    """One governable candidate derived from a durable source."""

    evidence_id: Identifier
    source_type: ContextSourceType
    case_id: Identifier
    authorization_scopes: frozenset[Identifier] = frozenset()
    applicable_tasks: frozenset[ContextTask]
    applicable_workflow_nodes: frozenset[Identifier] = frozenset()
    authority: AuthorityLevel
    created_at: datetime
    observed_at: datetime
    expires_at: datetime | None = None
    freshness: FreshnessState
    sensitivity: Sensitivity
    content: SafeText
    token_estimate: Annotated[int, Field(ge=1, le=100_000)]
    token_estimate_method: Literal["estimated_characters_div_4"] = TOKEN_ESTIMATE_METHOD
    priority: Annotated[int, Field(ge=0, le=100)] = 50
    relevance: Annotated[float, Field(ge=0, le=1)] = 0.5
    conflicts_with: frozenset[Identifier] = frozenset()
    supersedes: frozenset[Identifier] = frozenset()
    superseded_by: Identifier | None = None
    durable_fact_ids: tuple[Identifier, ...] = ()
    source_version: Identifier = "1"
    compactable: bool = True

    @field_validator("created_at", "observed_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("context timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timeline(self) -> Self:
        if self.observed_at < self.created_at:
            raise ValueError("observed_at must not precede created_at")
        if self.expires_at is not None and self.expires_at < self.observed_at:
            raise ValueError("expires_at must not precede observed_at")
        if (
            self.evidence_id in self.conflicts_with
            or self.evidence_id in self.supersedes
        ):
            raise ValueError(
                "context evidence cannot conflict with or supersede itself"
            )
        if self.token_estimate != estimate_tokens(self.content):
            raise ValueError("token_estimate must match estimated_characters_div_4")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


class ContextBuildRequest(ContextContract):
    case_id: Identifier
    task: ContextTask
    workflow_node: Identifier
    operator_id: Identifier
    operator_role: Identifier
    permissions: frozenset[Identifier]
    authorization_scopes: frozenset[Identifier]
    token_budget: Annotated[int, Field(ge=1, le=100_000)]
    mandatory_evidence_ids: frozenset[Identifier] = frozenset()
    approval_status: Identifier | None = None
    workflow_status: Identifier
    now: datetime
    schema_version: Literal["travelops.context.v1"] = CONTEXT_SCHEMA_VERSION
    policy_version: Literal["phase-12.1"] = CONTEXT_POLICY_VERSION

    @field_validator("now")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("context build time must be timezone-aware")
        return value


class SelectedContextItem(ContextContract):
    evidence_id: Identifier
    source_type: ContextSourceType
    authority: AuthorityLevel
    freshness: FreshnessState
    sensitivity: Sensitivity
    content: SafeText
    original_token_estimate: Annotated[int, Field(ge=1)]
    selected_token_estimate: Annotated[int, Field(ge=1)]
    compacted: bool = False
    durable_fact_ids: tuple[Identifier, ...]
    conflicts_with: frozenset[Identifier]
    supersedes: frozenset[Identifier]


class SelectionRecord(ContextContract):
    evidence_id: Identifier
    disposition: SelectionDisposition
    reason: SelectionReason
    mandatory: bool
    token_estimate: Annotated[int, Field(ge=0)]
    detail: str = Field(max_length=300)


class GovernedTool(ContextContract):
    name: Identifier
    kind: Literal["read", "proposal", "write"]
    exposed: bool
    reason: Identifier
    token_estimate: Annotated[int, Field(ge=0)] = 0
    input_schema: dict[str, object] | None = None


class CacheStatus(ContextContract):
    hit: bool
    key_reference: Identifier
    cache_version: Literal["phase-12.1"] = CONTEXT_CACHE_VERSION


class SummaryProvenance(ContextContract):
    summary_id: Identifier
    referenced_evidence_ids: tuple[Identifier, ...]
    valid: bool
    invalidation_reason: str | None = Field(default=None, max_length=300)


class ContextBuildResult(ContextContract):
    schema_version: Literal["travelops.context.v1"] = CONTEXT_SCHEMA_VERSION
    policy_version: Literal["phase-12.1"] = CONTEXT_POLICY_VERSION
    build_id: Identifier
    status: BuildStatus
    case_id: Identifier
    task: ContextTask
    workflow_node: Identifier
    selected: tuple[SelectedContextItem, ...]
    decisions: tuple[SelectionRecord, ...]
    token_accounting: TokenAccounting
    mandatory_evidence_coverage: Annotated[float, Field(ge=0, le=1)]
    stale_rejection_count: Annotated[int, Field(ge=0)]
    unauthorized_rejection_count: Annotated[int, Field(ge=0)]
    cross_case_rejection_count: Annotated[int, Field(ge=0)]
    conflict_count: Annotated[int, Field(ge=0)]
    compacted_count: Annotated[int, Field(ge=0)]
    excluded_count: Annotated[int, Field(ge=0)]
    cache: CacheStatus
    selection_latency_ms: Annotated[float, Field(ge=0)]
    tools: tuple[GovernedTool, ...]
    summary_provenance: tuple[SummaryProvenance, ...] = ()
    escalation_reason: str | None = Field(default=None, max_length=500)

    def canonical_json(self) -> str:
        """Serialize with stable key and collection ordering."""

        return _canonical_json(self.model_dump(mode="json"))


def estimate_tokens(value: str) -> int:
    """Return an explicitly labelled conservative provider-neutral estimate."""

    return max(1, (len(value) + 3) // 4)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
