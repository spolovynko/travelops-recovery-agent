"""Contract tests for the read-only recovery browser API."""

from fastapi.testclient import TestClient

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.query_models import (
    AlternativeItinerary,
    AlternativeSearchRequirements,
    FlightStatus,
    ItineraryValidationResult,
    OperationalFlightStatus,
    RecoveryCaseQueueItem,
)
from travelops_recovery_agent.application.recommendation_models import (
    EvidenceCompleteness,
    RecommendationOutcome,
    RecommendationResult,
)
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRule,
    ItineraryRuleResult,
    RuleStatus,
)


def complete_case(case_index: int = 0) -> CompleteRecoveryCase:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    booking = dataset.bookings[case_index]
    disruption = dataset.disruptions[case_index]
    passengers = tuple(
        passenger
        for passenger in dataset.passengers
        if passenger.id in booking.passenger_ids
    )
    flights_by_id = {flight.id: flight for flight in dataset.flights}
    return CompleteRecoveryCase(
        recovery_case=recovery_case,
        booking=booking,
        passengers=passengers,
        flights=tuple(flights_by_id[item.flight_id] for item in booking.segments),
        disruption=disruption,
        policy=dataset.policies[0],
    )


class RecoveryQueryServiceStub:
    def __init__(self, case: CompleteRecoveryCase | None = None) -> None:
        self.case = case
        self.fail = False

    def list_recovery_cases(self) -> tuple[RecoveryCaseQueueItem, ...]:
        if self.fail:
            raise RuntimeError("postgresql://unsafe-secret")
        if self.case is None:
            return ()
        disruption = self.case.disruption
        affected = next(
            flight
            for flight in self.case.flights
            if flight.id == disruption.affected_flight_id
        )
        status = self.get_flight_status(affected.id)
        assert status is not None
        return (
            RecoveryCaseQueueItem(
                recovery_case=self.case.recovery_case,
                booking=self.case.booking,
                passenger_count=len(self.case.passengers),
                itinerary=self.case.flights,
                disruption=disruption,
                affected_flight_status=status,
            ),
        )

    def recommend(self, case_id: str) -> RecommendationResult:
        if self.fail:
            raise RuntimeError("postgresql://unsafe-secret")
        return RecommendationResult(
            case_id=case_id,
            outcome=RecommendationOutcome.NO_SAFE_OPTION,
            evidence_completeness=EvidenceCompleteness.COMPLETE,
            escalation_reason="No test option passed every rule.",
            ranking_method="stable test ranking",
        )

    def get_recovery_case(self, case_id: str) -> CompleteRecoveryCase | None:
        if self.fail:
            raise RuntimeError("postgresql://unsafe-secret")
        return (
            self.case if self.case and self.case.recovery_case.id == case_id else None
        )

    def get_flight_status(self, flight_id: str) -> FlightStatus | None:
        if self.case is None:
            return None
        flight = next(
            (item for item in self.case.flights if item.id == flight_id), None
        )
        if flight is None:
            return None
        disruption = self.case.disruption
        affected = flight.id == disruption.affected_flight_id
        if affected and disruption.details.type.value == "delayed_flight":
            status = OperationalFlightStatus.DELAYED
            delay_minutes = 30
        else:
            status = OperationalFlightStatus.SCHEDULED
            delay_minutes = None
        return FlightStatus(
            flight=flight,
            status=status,
            delay_minutes=delay_minutes,
            cancellation_reason=None,
            related_disruptions=(disruption,) if affected else (),
        )

    def search_alternative_itineraries(
        self, requirements: AlternativeSearchRequirements
    ) -> tuple[AlternativeItinerary, ...]:
        if self.case is None:
            return ()
        return (
            AlternativeItinerary(
                flights=self.case.flights,
                connection_minutes=(90,),
            ),
        )

    def validate_itinerary(
        self, flight_ids: tuple[str, ...]
    ) -> ItineraryValidationResult:
        return ItineraryValidationResult(
            flight_ids=flight_ids,
            valid=True,
            rules=(
                ItineraryRuleResult(
                    rule=ItineraryRule.FLIGHTS_EXIST,
                    status=RuleStatus.PASSED,
                    reason="every requested flight exists in stored business data",
                ),
            ),
        )


def client(service: RecoveryQueryServiceStub) -> TestClient:
    return TestClient(create_app(Settings(environment=Environment.TEST), service))


def test_queue_and_workspace_return_minimized_structured_facts() -> None:
    service = RecoveryQueryServiceStub(complete_case())
    with client(service) as test_client:
        queue = test_client.get("/api/v1/recovery-cases")
        workspace = test_client.get("/api/v1/recovery-cases/CASE-0001")

    assert queue.status_code == 200
    assert queue.json()["cases"][0]["route"] == {
        "origin": "ZRA",
        "destination": "XLC",
    }
    assert "passengers" not in queue.text
    assert workspace.status_code == 200
    assert workspace.json()["passengers"] == [
        {"passenger_id": "PAX-0001", "display_name": "Mina Vale"}
    ]
    assert workspace.json()["itinerary"][0]["operational_status"] == "delayed"
    assert workspace.json()["policy"]["policy_id"] == "POL-STANDARD"
    assert workspace.json()["recommendation"]["outcome"] == "no_safe_option"


def test_recommendation_route_returns_a_typed_escalation() -> None:
    service = RecoveryQueryServiceStub(complete_case())
    with client(service) as test_client:
        response = test_client.get("/api/v1/recovery-cases/CASE-0001/recommendation")

    assert response.status_code == 200
    assert response.json()["outcome"] == "no_safe_option"
    assert response.json()["recommended_itinerary"] is None


def test_queue_empty_missing_case_and_dependency_failure_are_safe() -> None:
    service = RecoveryQueryServiceStub()
    with client(service) as test_client:
        empty = test_client.get("/api/v1/recovery-cases")
        missing = test_client.get("/api/v1/recovery-cases/CASE-9999")
        health = test_client.get("/health")
        service.fail = True
        unavailable = test_client.get("/api/v1/recovery-cases")

    assert empty.json() == {"cases": []}
    assert missing.status_code == 404
    assert health.json() == {"status": "ok"}
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "service_unavailable"
    assert "unsafe-secret" not in unavailable.text


def test_recovery_route_is_safe_without_database_configuration() -> None:
    with TestClient(create_app(Settings(environment=Environment.TEST))) as test_client:
        response = test_client.get("/api/v1/recovery-cases")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Recovery data is temporarily unavailable.",
            "retryable": True,
        }
    }


def test_search_and_validation_are_read_only_structured_queries() -> None:
    service = RecoveryQueryServiceStub(complete_case())
    with client(service) as test_client:
        search = test_client.post(
            "/api/v1/alternative-itineraries/search",
            json={
                "case_id": "CASE-0001",
                "earliest_departure": "2026-01-15T11:00:00Z",
                "latest_arrival": "2026-01-16T11:00:00Z",
                "max_connections": 1,
            },
        )
        candidate = search.json()["candidates"][0]
        validation = test_client.post(
            "/api/v1/itineraries/validate",
            json={
                "case_id": "CASE-0001",
                "candidate_id": candidate["candidate_id"],
                "flight_ids": [item["flight_id"] for item in candidate["segments"]],
            },
        )

    assert search.status_code == 200
    assert search.json()["inventory_status"] == "not_evaluated"
    assert validation.status_code == 200
    assert validation.json()["structurally_valid"] is True
    assert [item["status"] for item in validation.json()["rules"]] == [
        "passed",
        "deferred",
        "deferred",
        "deferred",
    ]


def test_search_request_validation_rejects_an_invalid_window() -> None:
    with client(RecoveryQueryServiceStub(complete_case())) as test_client:
        response = test_client.post(
            "/api/v1/alternative-itineraries/search",
            json={
                "case_id": "CASE-0001",
                "earliest_departure": "2026-01-16T11:00:00Z",
                "latest_arrival": "2026-01-15T11:00:00Z",
                "max_connections": 1,
            },
        )

    assert response.status_code == 422


def test_openapi_publishes_read_only_recovery_and_phase_eight_workflow_routes() -> None:
    schema = create_app(
        Settings(environment=Environment.TEST), RecoveryQueryServiceStub()
    ).openapi()

    assert set(schema["paths"]) == {
        "/health",
        "/api/v1/recovery-cases",
        "/api/v1/recovery-cases/{case_id}",
        "/api/v1/recovery-cases/{case_id}/recommendation",
        "/api/v1/alternative-itineraries/search",
        "/api/v1/itineraries/validate",
        "/api/v1/recovery-cases/{case_id}/workflow-runs",
        "/api/v1/workflow-runs/{run_id}",
        "/api/v1/workflow-runs/{run_id}/events",
        "/api/v1/workflow-runs/{run_id}/cancel",
        "/api/v1/workflow-runs/{run_id}/resume",
        "/api/v1/recovery-cases/{case_id}/proposal",
        "/api/v1/proposals/{proposal_id}",
        "/api/v1/proposals/{proposal_id}/approve",
        "/api/v1/proposals/{proposal_id}/reject",
        "/api/v1/proposals/{proposal_id}/execute",
        "/api/v1/proposals/{proposal_id}/execution",
        "/api/v1/proposals/{proposal_id}/audit",
    }
