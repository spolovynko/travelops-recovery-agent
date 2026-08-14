"""Immutable Phase 10 contracts for proposal, approval, and safe execution."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from travelops_recovery_agent.application.recommendation_models import (
    EvidenceCompleteness,
    EvidenceReference,
    RecommendationOption,
)


class ProposalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ProposalStatus(StrEnum):
    DRAFTED = "drafted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVALIDATION_FAILED = "revalidation_failed"
    EXECUTING = "executing"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class DecisionType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RevalidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApproverRequirement(ProposalContract):
    required_role: str = "recovery_operator"
    self_approval_prohibited: bool = True


class ProposalDecision(ProposalContract):
    decision: DecisionType
    actor_id: str
    actor_role: str
    proposal_version: Annotated[int, Field(gt=0)]
    itinerary_fingerprint: str
    decided_at: datetime
    reason: str | None = None


class RevalidationResult(ProposalContract):
    status: RevalidationStatus
    checked_at: datetime | None = None
    checks: tuple[str, ...] = ()
    failure_reasons: tuple[str, ...] = ()


class ExecutionResult(ProposalContract):
    status: ExecutionStatus
    execution_id: str
    idempotency_key_hash: str
    booking_id: str
    executed_at: datetime
    original_flight_ids: tuple[str, ...]
    replacement_flight_ids: tuple[str, ...]
    provider: str = "repository_synthetic_v1"


class AuditRecord(ProposalContract):
    audit_id: str
    sequence: Annotated[int, Field(gt=0)]
    proposal_id: str
    event_type: str
    actor_id: str
    occurred_at: datetime
    correlation_id: str
    details: dict[str, object]


class RecoveryProposal(ProposalContract):
    proposal_id: str
    version: Annotated[int, Field(gt=0)]
    case_id: str
    booking_id: str
    recommendation_reference: str
    validation_reference: str
    proposed_itinerary: RecommendationOption
    itinerary_fingerprint: str
    evidence_snapshot: tuple[EvidenceReference, ...]
    evidence_completeness: EvidenceCompleteness
    evidence_fingerprint: str
    created_at: datetime
    expires_at: datetime
    created_by: str
    status: ProposalStatus
    required_approver: ApproverRequirement
    decision: ProposalDecision | None = None
    execution_eligible: bool
    revalidation: RevalidationResult = RevalidationResult(
        status=RevalidationStatus.NOT_RUN
    )
    execution_result: ExecutionResult | None = None
    failure_reasons: tuple[str, ...] = ()
    escalation_reasons: tuple[str, ...] = ()
    workflow_run_id: str | None = None
    correlation_id: str

    @field_validator("created_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("proposal timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def enforce_shape(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("proposal expiry must follow creation")
        if not self.proposed_itinerary.validation.valid:
            raise ValueError("a proposal requires a validated itinerary")
        eligible = self.status is ProposalStatus.APPROVED and self.decision is not None
        if self.execution_eligible != eligible:
            raise ValueError("execution eligibility must be derived from status")
        if self.status is ProposalStatus.EXECUTED and self.execution_result is None:
            raise ValueError("executed proposals require a result")
        return self


class ProposalWithAudit(ProposalContract):
    proposal: RecoveryProposal
    audit_history: tuple[AuditRecord, ...]


VALID_PROPOSAL_TRANSITIONS: dict[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.DRAFTED: frozenset({ProposalStatus.AWAITING_APPROVAL}),
    ProposalStatus.AWAITING_APPROVAL: frozenset(
        {ProposalStatus.APPROVED, ProposalStatus.REJECTED, ProposalStatus.EXPIRED}
    ),
    ProposalStatus.APPROVED: frozenset(
        {
            ProposalStatus.EXPIRED,
            ProposalStatus.REVALIDATION_FAILED,
            ProposalStatus.EXECUTING,
        }
    ),
    ProposalStatus.EXECUTING: frozenset(
        {ProposalStatus.EXECUTED, ProposalStatus.EXECUTION_FAILED}
    ),
    ProposalStatus.REJECTED: frozenset(),
    ProposalStatus.EXPIRED: frozenset(),
    ProposalStatus.REVALIDATION_FAILED: frozenset(),
    ProposalStatus.EXECUTED: frozenset(),
    ProposalStatus.EXECUTION_FAILED: frozenset(),
}


def require_transition(current: ProposalStatus, target: ProposalStatus) -> None:
    if target not in VALID_PROPOSAL_TRANSITIONS[current]:
        raise ValueError(
            f"invalid proposal transition: {current.value} -> {target.value}"
        )
