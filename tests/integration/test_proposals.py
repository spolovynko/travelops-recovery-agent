"""Real PostgreSQL safety tests for Phase 10 proposal execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.application.proposal_models import (
    ProposalStatus,
    ProposalWithAudit,
)
from travelops_recovery_agent.application.proposals import (
    ProposalError,
    ProposalService,
)
from travelops_recovery_agent.application.services import RecoveryDataService
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.models import (
    BookingChangeRecord,
    ExecutionAttemptRecord,
    FlightAvailabilityEvidenceRecord,
    ItinerarySegmentRecord,
    ProposalAuditRecord,
)
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


class FailingSyntheticProvider:
    name = "failing_test_provider"

    def apply(
        self,
        session: Session,
        *,
        proposal: object,
        execution_id: str,
        now: datetime,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        del session, proposal, execution_id, now
        raise RuntimeError("simulated provider failure")


def _service(factory: SessionFactory) -> ProposalService:
    RecoveryDataService(
        partial(SqlAlchemyRecoveryDataUnitOfWork, factory), Environment.TEST
    ).seed(generate_dataset(seed=42))
    return ProposalService(factory, clock=lambda: NOW)


def _approved(
    service: ProposalService, case_id: str = "CASE-0002"
) -> ProposalWithAudit:
    created = service.create_or_get(
        case_id, actor_id="preparer", correlation_id="corr-create"
    )
    proposal = created.proposal
    return service.decide(
        proposal.proposal_id,
        version=proposal.version,
        itinerary_fingerprint=proposal.itinerary_fingerprint,
        approve=True,
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-approve",
    )


@pytest.mark.integration
def test_approved_proposal_executes_once_and_replay_returns_original_result(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    approved = _approved(service)

    first = service.execute(
        approved.proposal.proposal_id,
        idempotency_key="execute-case-1",
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-execute",
    )
    replay = service.execute(
        approved.proposal.proposal_id,
        idempotency_key="execute-case-1",
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-replay",
    )

    assert first == replay
    assert first.proposal.status is ProposalStatus.EXECUTED
    assert first.proposal.revalidation.status.value == "passed"
    assert first.proposal.execution_result is not None
    with clean_session_factory() as session:
        assert session.scalar(select(func.count(BookingChangeRecord.id))) == 1
        assert session.scalar(select(func.count(ExecutionAttemptRecord.id))) == 1
        assert session.scalar(select(func.count(ItinerarySegmentRecord.id))) == 20


@pytest.mark.integration
def test_changed_seat_evidence_stops_execution_and_escalates(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    approved = _approved(service)
    flight_id = approved.proposal.proposed_itinerary.segments[0].flight_id
    with clean_session_factory.begin() as session:
        session.execute(
            update(FlightAvailabilityEvidenceRecord)
            .where(FlightAvailabilityEvidenceRecord.flight_id == flight_id)
            .values(available_seats=0, observed_at=NOW)
        )

    result = service.execute(
        approved.proposal.proposal_id,
        idempotency_key="changed-evidence",
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-execute",
    )

    assert result.proposal.status is ProposalStatus.REVALIDATION_FAILED
    assert result.proposal.failure_reasons
    assert result.proposal.escalation_reasons
    with clean_session_factory() as session:
        assert session.scalar(select(func.count(BookingChangeRecord.id))) == 0
        assert session.scalar(select(func.count(ExecutionAttemptRecord.id))) == 1


@pytest.mark.integration
def test_provider_failure_rolls_back_booking_change_and_records_failed_attempt(
    clean_session_factory: SessionFactory,
) -> None:
    base = _service(clean_session_factory)
    approved = _approved(base)
    service = ProposalService(
        clean_session_factory,
        clock=lambda: NOW,
        provider=FailingSyntheticProvider(),
    )
    result = service.execute(
        approved.proposal.proposal_id,
        idempotency_key="provider-failure",
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-execute",
    )
    assert result.proposal.status is ProposalStatus.EXECUTION_FAILED
    assert result.proposal.failure_reasons
    with clean_session_factory() as session:
        assert session.scalar(select(func.count(BookingChangeRecord.id))) == 0
        attempt = session.scalar(select(ExecutionAttemptRecord))
        assert attempt is not None
        assert attempt.status == "failed"


@pytest.mark.integration
def test_concurrent_same_request_applies_at_most_one_booking_change(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    approved = _approved(service)

    def execute() -> ProposalWithAudit:
        return service.execute(
            approved.proposal.proposal_id,
            idempotency_key="concurrent-execution",
            actor_id="operator-1",
            actor_role="recovery_operator",
            correlation_id="corr-concurrent",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: execute(), range(2)))
    assert all(item.proposal.status is ProposalStatus.EXECUTED for item in results)
    assert results[0].proposal.execution_result == results[1].proposal.execution_result
    with clean_session_factory() as session:
        assert session.scalar(select(func.count(BookingChangeRecord.id))) == 1
        assert session.scalar(select(func.count(ExecutionAttemptRecord.id))) == 1


@pytest.mark.integration
def test_reusing_idempotency_key_for_another_proposal_fails_safely(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    first = _approved(service, "CASE-0002")
    service.execute(
        first.proposal.proposal_id,
        idempotency_key="shared-key",
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr-first",
    )
    second = _approved(service, "CASE-0003")
    with pytest.raises(ProposalError) as raised:
        service.execute(
            second.proposal.proposal_id,
            idempotency_key="shared-key",
            actor_id="operator-1",
            actor_role="recovery_operator",
            correlation_id="corr-second",
        )
    assert raised.value.code == "idempotency_conflict"


@pytest.mark.integration
def test_expired_proposal_requires_a_new_version_and_new_approval(
    clean_session_factory: SessionFactory,
) -> None:
    RecoveryDataService(
        partial(SqlAlchemyRecoveryDataUnitOfWork, clean_session_factory),
        Environment.TEST,
    ).seed(generate_dataset(seed=42))
    current = [NOW]
    service = ProposalService(
        clean_session_factory,
        clock=lambda: current[0],
        ttl=timedelta(minutes=1),
    )
    first = service.create_or_get(
        "CASE-0001", actor_id="preparer", correlation_id="corr"
    ).proposal
    current[0] = NOW + timedelta(minutes=2)
    with pytest.raises(ProposalError) as raised:
        service.decide(
            first.proposal_id,
            version=first.version,
            itinerary_fingerprint=first.itinerary_fingerprint,
            approve=True,
            actor_id="operator-1",
            actor_role="recovery_operator",
            correlation_id="corr",
        )
    assert raised.value.code == "proposal_expired"
    assert service.get(first.proposal_id).proposal.status is ProposalStatus.EXPIRED
    second = service.create_or_get(
        "CASE-0001", actor_id="preparer", correlation_id="corr-new"
    ).proposal
    assert second.version == first.version + 1
    assert second.proposal_id != first.proposal_id


@pytest.mark.integration
def test_stale_self_and_conflicting_decisions_are_rejected(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    created = service.create_or_get(
        "CASE-0001", actor_id="preparer", correlation_id="corr"
    ).proposal
    with pytest.raises(ProposalError, match="exact proposal version"):
        service.decide(
            created.proposal_id,
            version=created.version + 1,
            itinerary_fingerprint=created.itinerary_fingerprint,
            approve=True,
            actor_id="operator-1",
            actor_role="recovery_operator",
            correlation_id="corr",
        )
    with pytest.raises(ProposalError, match="creator cannot"):
        service.decide(
            created.proposal_id,
            version=created.version,
            itinerary_fingerprint=created.itinerary_fingerprint,
            approve=True,
            actor_id="preparer",
            actor_role="recovery_operator",
            correlation_id="corr",
        )
    approved = service.decide(
        created.proposal_id,
        version=created.version,
        itinerary_fingerprint=created.itinerary_fingerprint,
        approve=True,
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id="corr",
    )
    with pytest.raises(ProposalError, match="already has a decision"):
        service.decide(
            approved.proposal.proposal_id,
            version=created.version,
            itinerary_fingerprint=created.itinerary_fingerprint,
            approve=False,
            reason="conflict",
            actor_id="operator-2",
            actor_role="recovery_operator",
            correlation_id="corr",
        )


@pytest.mark.integration
def test_database_rejects_audit_update(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    proposal = service.create_or_get(
        "CASE-0001", actor_id="preparer", correlation_id="corr"
    ).proposal
    with pytest.raises(DBAPIError), clean_session_factory.begin() as session:
        session.execute(
            update(ProposalAuditRecord)
            .where(ProposalAuditRecord.proposal_id == proposal.proposal_id)
            .values(actor_id="tampered")
        )


@pytest.mark.integration
def test_proposal_api_requires_actor_and_exposes_approval_execution_and_audit(
    clean_session_factory: SessionFactory,
) -> None:
    service = _service(clean_session_factory)
    with TestClient(
        create_app(Settings(environment=Environment.TEST), proposal_service=service)
    ) as client:
        missing = client.post("/api/v1/recovery-cases/CASE-0002/proposal", json={})
        assert missing.status_code == 401
        created = client.post(
            "/api/v1/recovery-cases/CASE-0002/proposal",
            json={},
            headers={"X-Actor-ID": "preparer"},
        )
        assert created.status_code == 200
        proposal = created.json()["proposal"]
        approved = client.post(
            f"/api/v1/proposals/{proposal['proposal_id']}/approve",
            json={
                "version": proposal["version"],
                "itinerary_fingerprint": proposal["itinerary_fingerprint"],
            },
            headers={
                "X-Actor-ID": "operator-1",
                "X-Actor-Role": "recovery_operator",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["proposal"]["execution_eligible"] is True
        executed = client.post(
            f"/api/v1/proposals/{proposal['proposal_id']}/execute",
            json={"idempotency_key": "api-execute-case-1"},
            headers={
                "X-Actor-ID": "operator-1",
                "X-Actor-Role": "recovery_operator",
            },
        )
        assert executed.status_code == 200
        assert executed.json()["proposal"]["status"] == "executed"
        audit = client.get(
            f"/api/v1/proposals/{proposal['proposal_id']}/audit",
            headers={"X-Actor-ID": "auditor"},
        )
        assert [item["event_type"] for item in audit.json()["audit_history"]] == [
            "proposal.created",
            "proposal.approved",
            "execution.started",
            "proposal.revalidated",
            "execution.succeeded",
        ]
