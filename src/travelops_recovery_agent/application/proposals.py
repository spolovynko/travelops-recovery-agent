"""Application-owned Phase 10 proposal lifecycle and synthetic execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from travelops_recovery_agent.application.proposal_models import (
    ApproverRequirement,
    AuditRecord,
    DecisionType,
    ExecutionResult,
    ExecutionStatus,
    ProposalDecision,
    ProposalStatus,
    ProposalWithAudit,
    RecoveryProposal,
    RevalidationResult,
    RevalidationStatus,
    require_transition,
)
from travelops_recovery_agent.application.recommendation_models import (
    EvidenceCompleteness,
    EvidenceReference,
    RecommendationOption,
    RecommendationOutcome,
)
from travelops_recovery_agent.application.recommendations import RecommendationService
from travelops_recovery_agent.application.repositories import RecoveryDataRepository
from travelops_recovery_agent.persistence.models import (
    BookingChangeRecord,
    BookingPassengerRecord,
    BookingRecord,
    DisruptionPolicyRecord,
    DisruptionPolicyTypeRecord,
    DisruptionRecord,
    ExecutionAttemptRecord,
    FlightAvailabilityEvidenceRecord,
    FlightRecord,
    ItinerarySegmentRecord,
    ProposalApprovalRecord,
    ProposalAuditRecord,
    RebookingProposalRecord,
    RecoveryCaseRecord,
    TicketRuleEvidenceRecord,
)
from travelops_recovery_agent.persistence.repositories import (
    SqlAlchemyRecoveryDataRepository,
)
from travelops_recovery_agent.persistence.session import SessionFactory


class ProposalError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class SyntheticExecutionProvider(Protocol):
    """Provider-independent effect boundary; Phase 10 supplies a repository adapter."""

    name: str

    def apply(
        self,
        session: Session,
        *,
        proposal: RebookingProposalRecord,
        execution_id: str,
        now: datetime,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]: ...


class RepositorySyntheticExecutionProvider:
    name = "repository_synthetic_v1"

    def apply(
        self,
        session: Session,
        *,
        proposal: RebookingProposalRecord,
        execution_id: str,
        now: datetime,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        booking = session.scalar(
            select(BookingRecord)
            .where(BookingRecord.id == proposal.booking_id)
            .with_for_update()
        )
        if booking is None:
            raise ProposalError("booking_missing", "The booking no longer exists.")
        original = session.scalars(
            select(ItinerarySegmentRecord)
            .where(ItinerarySegmentRecord.booking_id == proposal.booking_id)
            .order_by(ItinerarySegmentRecord.sequence)
            .with_for_update()
        ).all()
        original_json = [
            {
                "segment_id": item.id,
                "sequence": item.sequence,
                "flight_id": item.flight_id,
            }
            for item in original
        ]
        itinerary = RecommendationOption.model_validate(proposal.itinerary)
        replacement_json = [
            {"sequence": index, "flight_id": item.flight_id}
            for index, item in enumerate(itinerary.segments, start=1)
        ]
        original_ids = tuple(str(item["flight_id"]) for item in original_json)
        replacement_ids = tuple(item.flight_id for item in itinerary.segments)
        if original_ids == replacement_ids:
            raise ProposalError(
                "no_booking_change",
                "The proposed itinerary is already the booking's current itinerary.",
            )
        session.add(
            BookingChangeRecord(
                id=str(uuid4()),
                proposal_id=proposal.id,
                booking_id=proposal.booking_id,
                original_itinerary=original_json,
                replacement_itinerary=replacement_json,
                applied_at=now,
            )
        )
        return (
            original_ids,
            replacement_ids,
        )


class _BorrowedUnitOfWork:
    """Expose one already-locked transaction to the Phase 9 recommendation service."""

    repository: RecoveryDataRepository

    def __init__(self, session: Session) -> None:
        self.repository = SqlAlchemyRecoveryDataRepository(session)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ProposalService:
    """Fail-closed lifecycle with row locks, immutable audits, and effect idempotency."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ttl: timedelta = timedelta(minutes=30),
        provider: SyntheticExecutionProvider | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock
        self._ttl = ttl
        self._provider = provider or RepositorySyntheticExecutionProvider()

    def create_or_get(
        self,
        case_id: str,
        *,
        actor_id: str,
        correlation_id: str,
        workflow_run_id: str | None = None,
    ) -> ProposalWithAudit:
        now = self._clock()
        with self._sessions.begin() as session:
            existing = session.scalar(
                select(RebookingProposalRecord)
                .where(
                    RebookingProposalRecord.case_id == case_id,
                    RebookingProposalRecord.status.in_(
                        ("awaiting_approval", "approved", "executing")
                    ),
                )
                .with_for_update()
            )
            if existing is not None and existing.expires_at > now:
                return self._view(session, existing)
            if existing is not None:
                self._transition(existing, ProposalStatus.EXPIRED)
                self._audit(
                    session,
                    existing,
                    "proposal.expired",
                    "system",
                    now,
                    correlation_id,
                    {},
                )
            latest = session.scalar(
                select(RebookingProposalRecord)
                .where(RebookingProposalRecord.case_id == case_id)
                .order_by(RebookingProposalRecord.version.desc())
                .limit(1)
            )
            if (
                existing is None
                and latest is not None
                and latest.status == ProposalStatus.EXECUTED.value
            ):
                return self._view(session, latest)

            recommendation = RecommendationService(
                lambda: _BorrowedUnitOfWork(session)
            ).recommend(case_id)
            if (
                recommendation.outcome is not RecommendationOutcome.RECOMMENDED
                or recommendation.recommended_itinerary is None
            ):
                raise ProposalError(
                    "no_safe_recommendation",
                    recommendation.escalation_reason
                    or "No validated recommendation can become a proposal.",
                    status_code=422,
                )
            complete_case = SqlAlchemyRecoveryDataRepository(session).get_complete_case(
                case_id
            )
            if complete_case is None:
                raise ProposalError(
                    "not_found", "Recovery case was not found.", status_code=404
                )
            version = (
                int(
                    session.scalar(
                        select(
                            func.coalesce(func.max(RebookingProposalRecord.version), 0)
                        ).where(RebookingProposalRecord.case_id == case_id)
                    )
                    or 0
                )
                + 1
            )
            option = recommendation.recommended_itinerary
            option_json = option.model_dump(mode="json")
            evidence_json = [
                item.model_dump(mode="json") for item in option.evidence_references
            ]
            proposal = RebookingProposalRecord(
                id=str(uuid4()),
                version=version,
                case_id=case_id,
                booking_id=complete_case.booking.id,
                recommendation_reference="recommendation:"
                + _fingerprint(recommendation.model_dump(mode="json")),
                validation_reference=f"validation:{option.option_id}:{_fingerprint(option_json)}",
                itinerary=option_json,
                itinerary_fingerprint=_fingerprint(option_json),
                evidence_snapshot=evidence_json,
                evidence_completeness=recommendation.evidence_completeness.value,
                evidence_fingerprint=_fingerprint(evidence_json),
                created_at=now,
                expires_at=now + self._ttl,
                created_by=actor_id,
                status=ProposalStatus.AWAITING_APPROVAL.value,
                required_role="recovery_operator",
                revalidation=RevalidationResult(
                    status=RevalidationStatus.NOT_RUN
                ).model_dump(mode="json"),
                execution_result=None,
                failure_reasons=[],
                escalation_reasons=[],
                workflow_run_id=workflow_run_id,
                correlation_id=correlation_id,
            )
            session.add(proposal)
            session.flush([proposal])
            self._audit(
                session,
                proposal,
                "proposal.created",
                actor_id,
                now,
                correlation_id,
                {
                    "version": version,
                    "recommendation_reference": proposal.recommendation_reference,
                    "validation_reference": proposal.validation_reference,
                    "evidence_fingerprint": proposal.evidence_fingerprint,
                    "itinerary_fingerprint": proposal.itinerary_fingerprint,
                    "workflow_run_id": workflow_run_id,
                },
            )
            session.flush()
            return self._view(session, proposal)

    def get(self, proposal_id: str) -> ProposalWithAudit:
        with self._sessions.begin() as session:
            proposal = self._get_locked(session, proposal_id)
            now = self._clock()
            if proposal.expires_at <= now and proposal.status in (
                ProposalStatus.AWAITING_APPROVAL.value,
                ProposalStatus.APPROVED.value,
            ):
                self._transition(proposal, ProposalStatus.EXPIRED)
                self._audit(
                    session,
                    proposal,
                    "proposal.expired",
                    "system",
                    now,
                    proposal.correlation_id,
                    {},
                )
            return self._view(session, proposal)

    def decide(
        self,
        proposal_id: str,
        *,
        version: int,
        itinerary_fingerprint: str,
        approve: bool,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        reason: str | None = None,
    ) -> ProposalWithAudit:
        now = self._clock()
        expired = False
        with self._sessions.begin() as expiry_session:
            expiry_proposal = self._get_locked(expiry_session, proposal_id)
            if (
                expiry_proposal.status == ProposalStatus.AWAITING_APPROVAL.value
                and expiry_proposal.expires_at <= now
            ):
                self._transition(expiry_proposal, ProposalStatus.EXPIRED)
                self._audit(
                    expiry_session,
                    expiry_proposal,
                    "proposal.expired",
                    "system",
                    now,
                    correlation_id,
                    {},
                )
                expired = True
        if expired:
            raise ProposalError("proposal_expired", "The proposal has expired.")
        with self._sessions.begin() as session:
            proposal = self._get_locked(session, proposal_id)
            prior = session.scalar(
                select(ProposalApprovalRecord).where(
                    ProposalApprovalRecord.proposal_id == proposal_id
                )
            )
            if prior is not None:
                same = (
                    prior.proposal_version == version
                    and prior.itinerary_fingerprint == itinerary_fingerprint
                    and prior.actor_id == actor_id
                    and prior.decision == ("approved" if approve else "rejected")
                )
                if same:
                    return self._view(session, proposal)
                raise ProposalError(
                    "conflicting_decision", "This proposal already has a decision."
                )
            if proposal.status != ProposalStatus.AWAITING_APPROVAL.value:
                raise ProposalError(
                    "proposal_not_awaiting_approval",
                    "The proposal cannot be decided in its current state.",
                )
            if proposal.expires_at <= now:
                self._transition(proposal, ProposalStatus.EXPIRED)
                self._audit(
                    session,
                    proposal,
                    "proposal.expired",
                    "system",
                    now,
                    correlation_id,
                    {},
                )
                raise ProposalError("proposal_expired", "The proposal has expired.")
            if (
                version != proposal.version
                or itinerary_fingerprint != proposal.itinerary_fingerprint
            ):
                raise ProposalError(
                    "stale_approval",
                    "Approval must bind to the exact proposal version and itinerary.",
                )
            if not actor_id or actor_role != proposal.required_role:
                raise ProposalError(
                    "unauthorized_actor",
                    "An authorized recovery operator is required.",
                    status_code=403,
                )
            if actor_id == proposal.created_by:
                raise ProposalError(
                    "self_approval_prohibited",
                    "The proposal creator cannot approve or reject it.",
                    status_code=403,
                )
            decision = DecisionType.APPROVED if approve else DecisionType.REJECTED
            if not approve and not reason:
                raise ProposalError(
                    "rejection_reason_required",
                    "A rejection reason is required.",
                    status_code=422,
                )
            session.add(
                ProposalApprovalRecord(
                    id=str(uuid4()),
                    proposal_id=proposal.id,
                    proposal_version=version,
                    decision=decision.value,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    itinerary_fingerprint=itinerary_fingerprint,
                    decided_at=now,
                    reason=reason,
                )
            )
            self._transition(
                proposal,
                ProposalStatus.APPROVED if approve else ProposalStatus.REJECTED,
            )
            self._audit(
                session,
                proposal,
                f"proposal.{decision.value}",
                actor_id,
                now,
                correlation_id,
                {
                    "version": version,
                    "itinerary_fingerprint": itinerary_fingerprint,
                    "reason": reason,
                },
            )
            session.flush()
            return self._view(session, proposal)

    def execute(
        self,
        proposal_id: str,
        *,
        idempotency_key: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
    ) -> ProposalWithAudit:
        if not idempotency_key or len(idempotency_key) > 128:
            raise ProposalError(
                "invalid_idempotency_key",
                "A valid idempotency key is required.",
                status_code=422,
            )
        request_fp = _fingerprint({"proposal_id": proposal_id, "actor_id": actor_id})
        now = self._clock()
        expired = False
        with self._sessions.begin() as expiry_session:
            expiry_proposal = self._get_locked(expiry_session, proposal_id)
            if (
                expiry_proposal.status == ProposalStatus.APPROVED.value
                and expiry_proposal.expires_at <= now
            ):
                self._transition(expiry_proposal, ProposalStatus.EXPIRED)
                self._audit(
                    expiry_session,
                    expiry_proposal,
                    "proposal.expired",
                    "system",
                    now,
                    correlation_id,
                    {},
                )
                expired = True
        if expired:
            raise ProposalError("proposal_expired", "The proposal has expired.")
        try:
            with self._sessions.begin() as session:
                proposal = self._get_locked(session, proposal_id)
                replay = session.scalar(
                    select(ExecutionAttemptRecord).where(
                        ExecutionAttemptRecord.idempotency_key == idempotency_key
                    )
                )
                if replay is not None:
                    if (
                        replay.proposal_id != proposal_id
                        or replay.request_fingerprint != request_fp
                    ):
                        raise ProposalError(
                            "idempotency_conflict",
                            "The idempotency key belongs to a different request.",
                        )
                    return self._view(session, proposal)
                if (
                    actor_role not in {proposal.required_role, "workflow_executor"}
                    or not actor_id
                ):
                    raise ProposalError(
                        "unauthorized_actor",
                        "An authorized recovery operator is required.",
                        status_code=403,
                    )
                approval = session.scalar(
                    select(ProposalApprovalRecord).where(
                        ProposalApprovalRecord.proposal_id == proposal.id,
                        ProposalApprovalRecord.decision == DecisionType.APPROVED.value,
                    )
                )
                if proposal.status != ProposalStatus.APPROVED.value or approval is None:
                    raise ProposalError(
                        "proposal_not_approved",
                        "Execution requires an authoritative stored approval.",
                    )
                if proposal.expires_at <= now or approval.decided_at > now:
                    self._transition(proposal, ProposalStatus.EXPIRED)
                    self._audit(
                        session,
                        proposal,
                        "proposal.expired",
                        "system",
                        now,
                        correlation_id,
                        {},
                    )
                    raise ProposalError(
                        "proposal_expired", "The proposal or approval has expired."
                    )
                if (
                    approval.proposal_version != proposal.version
                    or approval.itinerary_fingerprint != proposal.itinerary_fingerprint
                ):
                    raise ProposalError(
                        "stale_approval",
                        "Stored approval does not match the proposal exactly.",
                    )

                execution_id = str(uuid4())
                attempt = ExecutionAttemptRecord(
                    id=execution_id,
                    proposal_id=proposal.id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fp,
                    status="executing",
                    actor_id=actor_id,
                    started_at=now,
                    completed_at=None,
                    result=None,
                    failure_reason=None,
                )
                session.add(attempt)
                self._audit(
                    session,
                    proposal,
                    "execution.started",
                    actor_id,
                    now,
                    correlation_id,
                    {
                        "execution_id": execution_id,
                        "idempotency_key_hash": _fingerprint(idempotency_key),
                    },
                )

                # Lock all safety-critical source rows before recomputing Phase 9 evidence.
                session.scalars(
                    select(BookingRecord)
                    .where(BookingRecord.id == proposal.booking_id)
                    .with_for_update()
                ).all()
                session.scalars(
                    select(BookingPassengerRecord)
                    .where(BookingPassengerRecord.booking_id == proposal.booking_id)
                    .with_for_update()
                ).all()
                session.scalars(
                    select(ItinerarySegmentRecord)
                    .where(ItinerarySegmentRecord.booking_id == proposal.booking_id)
                    .with_for_update()
                ).all()
                session.scalars(
                    select(RecoveryCaseRecord)
                    .where(RecoveryCaseRecord.id == proposal.case_id)
                    .with_for_update()
                ).all()
                session.scalars(select(DisruptionPolicyRecord).with_for_update()).all()
                session.scalars(
                    select(DisruptionPolicyTypeRecord).with_for_update()
                ).all()
                session.scalars(select(FlightRecord).with_for_update()).all()
                session.scalars(select(DisruptionRecord).with_for_update()).all()
                session.scalars(
                    select(FlightAvailabilityEvidenceRecord).with_for_update()
                ).all()
                session.scalars(
                    select(TicketRuleEvidenceRecord)
                    .where(TicketRuleEvidenceRecord.booking_id == proposal.booking_id)
                    .with_for_update()
                ).all()
                fresh = RecommendationService(
                    lambda: _BorrowedUnitOfWork(session)
                ).recommend(proposal.case_id)
                option = next(
                    (
                        item
                        for item in fresh.option_results
                        if item.option_id
                        == RecommendationOption.model_validate(
                            proposal.itinerary
                        ).option_id
                    ),
                    None,
                )
                reasons: list[str] = []
                if option is None:
                    reasons.append("The approved itinerary is no longer present.")
                elif (
                    not option.validation.valid
                    or not option.validation.evidence_complete
                ):
                    reasons.extend(
                        option.validation.rejection_reasons
                        or ("Fresh evidence is incomplete.",)
                    )
                elif (
                    _fingerprint(option.model_dump(mode="json"))
                    != proposal.itinerary_fingerprint
                ):
                    reasons.append(
                        "The approved itinerary or its validation details changed."
                    )
                elif (
                    _fingerprint(
                        [
                            item.model_dump(mode="json")
                            for item in option.evidence_references
                        ]
                    )
                    != proposal.evidence_fingerprint
                ):
                    reasons.append("Safety-critical evidence changed after approval.")
                if reasons:
                    attempt.status = "failed"
                    attempt.completed_at = now
                    attempt.failure_reason = "Fresh safety evidence did not pass."
                    attempt.result = {
                        "status": "revalidation_failed",
                        "failure_reasons": reasons,
                    }
                    self._transition(proposal, ProposalStatus.REVALIDATION_FAILED)
                    proposal.failure_reasons = reasons
                    proposal.escalation_reasons = [
                        "Human review is required before a new proposal can be approved."
                    ]
                    proposal.revalidation = RevalidationResult(
                        status=RevalidationStatus.FAILED,
                        checked_at=now,
                        failure_reasons=tuple(reasons),
                    ).model_dump(mode="json")
                    self._audit(
                        session,
                        proposal,
                        "proposal.revalidation_failed",
                        actor_id,
                        now,
                        correlation_id,
                        {"reasons": reasons},
                    )
                    session.flush()
                    return self._view(session, proposal)

                checks = (
                    tuple(check.rule.value for check in option.validation.checks)
                    if option
                    else ()
                )
                proposal.revalidation = RevalidationResult(
                    status=RevalidationStatus.PASSED, checked_at=now, checks=checks
                ).model_dump(mode="json")
                self._audit(
                    session,
                    proposal,
                    "proposal.revalidated",
                    actor_id,
                    now,
                    correlation_id,
                    {"checks": list(checks)},
                )
                self._transition(proposal, ProposalStatus.EXECUTING)
                try:
                    with session.begin_nested():
                        original, replacement = self._provider.apply(
                            session,
                            proposal=proposal,
                            execution_id=execution_id,
                            now=now,
                        )
                        session.flush()
                except Exception:
                    attempt.status = "failed"
                    attempt.completed_at = now
                    attempt.failure_reason = "The synthetic provider failed safely."
                    proposal.failure_reasons = [
                        "The synthetic booking provider failed before commit."
                    ]
                    proposal.escalation_reasons = [
                        "Inspect the execution attempt before preparing a new proposal."
                    ]
                    self._transition(proposal, ProposalStatus.EXECUTION_FAILED)
                    self._audit(
                        session,
                        proposal,
                        "execution.failed",
                        actor_id,
                        now,
                        correlation_id,
                        {
                            "execution_id": execution_id,
                            "reason": "synthetic_provider_failure",
                            "idempotency_key_hash": _fingerprint(idempotency_key),
                        },
                    )
                    session.flush()
                    return self._view(session, proposal)
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCEEDED,
                    execution_id=execution_id,
                    idempotency_key_hash=_fingerprint(idempotency_key),
                    booking_id=proposal.booking_id,
                    executed_at=now,
                    original_flight_ids=original,
                    replacement_flight_ids=replacement,
                    provider=self._provider.name,
                )
                attempt.status = "succeeded"
                attempt.completed_at = now
                attempt.result = result.model_dump(mode="json")
                proposal.execution_result = result.model_dump(mode="json")
                self._transition(proposal, ProposalStatus.EXECUTED)
                self._audit(
                    session,
                    proposal,
                    "execution.succeeded",
                    actor_id,
                    now,
                    correlation_id,
                    {
                        "execution_id": execution_id,
                        "booking_before": list(original),
                        "booking_after": list(replacement),
                        "idempotency_key_hash": _fingerprint(idempotency_key),
                    },
                )
                session.flush()
                return self._view(session, proposal)
        except IntegrityError as error:
            raise ProposalError(
                "concurrent_execution_conflict",
                "Another execution already applied this booking change.",
            ) from error

    @staticmethod
    def _transition(record: RebookingProposalRecord, target: ProposalStatus) -> None:
        require_transition(ProposalStatus(record.status), target)
        record.status = target.value

    @staticmethod
    def _get_locked(session: Session, proposal_id: str) -> RebookingProposalRecord:
        value = session.scalar(
            select(RebookingProposalRecord)
            .where(RebookingProposalRecord.id == proposal_id)
            .with_for_update()
        )
        if value is None:
            raise ProposalError("not_found", "Proposal was not found.", status_code=404)
        return value

    @staticmethod
    def _audit(
        session: Session,
        proposal: RebookingProposalRecord,
        event_type: str,
        actor_id: str,
        occurred_at: datetime,
        correlation_id: str,
        details: dict[str, object],
    ) -> None:
        session.add(
            ProposalAuditRecord(
                id=str(uuid4()),
                proposal_id=proposal.id,
                event_type=event_type,
                actor_id=actor_id,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                details=details,
            )
        )

    @staticmethod
    def _view(session: Session, record: RebookingProposalRecord) -> ProposalWithAudit:
        decision_record = session.scalar(
            select(ProposalApprovalRecord).where(
                ProposalApprovalRecord.proposal_id == record.id
            )
        )
        decision = (
            None
            if decision_record is None
            else ProposalDecision(
                decision=DecisionType(decision_record.decision),
                actor_id=decision_record.actor_id,
                actor_role=decision_record.actor_role,
                proposal_version=decision_record.proposal_version,
                itinerary_fingerprint=decision_record.itinerary_fingerprint,
                decided_at=decision_record.decided_at,
                reason=decision_record.reason,
            )
        )
        status = ProposalStatus(record.status)
        proposal = RecoveryProposal(
            proposal_id=record.id,
            version=record.version,
            case_id=record.case_id,
            booking_id=record.booking_id,
            recommendation_reference=record.recommendation_reference,
            validation_reference=record.validation_reference,
            proposed_itinerary=RecommendationOption.model_validate(record.itinerary),
            itinerary_fingerprint=record.itinerary_fingerprint,
            evidence_snapshot=tuple(
                EvidenceReference.model_validate(item)
                for item in record.evidence_snapshot
            ),
            evidence_completeness=EvidenceCompleteness(record.evidence_completeness),
            evidence_fingerprint=record.evidence_fingerprint,
            created_at=record.created_at,
            expires_at=record.expires_at,
            created_by=record.created_by,
            status=status,
            required_approver=ApproverRequirement(required_role=record.required_role),
            decision=decision,
            execution_eligible=status is ProposalStatus.APPROVED
            and decision is not None,
            revalidation=RevalidationResult.model_validate(record.revalidation),
            execution_result=ExecutionResult.model_validate(record.execution_result)
            if record.execution_result
            else None,
            failure_reasons=tuple(record.failure_reasons),
            escalation_reasons=tuple(record.escalation_reasons),
            workflow_run_id=record.workflow_run_id,
            correlation_id=record.correlation_id,
        )
        rows = session.scalars(
            select(ProposalAuditRecord)
            .where(ProposalAuditRecord.proposal_id == record.id)
            .order_by(ProposalAuditRecord.sequence)
        ).all()
        return ProposalWithAudit(
            proposal=proposal,
            audit_history=tuple(
                AuditRecord(
                    audit_id=item.id,
                    sequence=item.sequence,
                    proposal_id=item.proposal_id,
                    event_type=item.event_type,
                    actor_id=item.actor_id,
                    occurred_at=item.occurred_at,
                    correlation_id=item.correlation_id,
                    details=item.details,
                )
                for item in rows
            ),
        )
