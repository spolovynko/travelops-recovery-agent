"""Deterministic Phase 9 validation and recommendation benchmarks."""

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self, cast

import pytest

from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.query_models import (
    AvailabilityEvidence,
    FlightStatus,
    FlightWithDisruptions,
    OperationalFlightStatus,
    TicketRuleEvidence,
)
from travelops_recovery_agent.application.recommendation_models import (
    RecommendationOption,
    RecommendationOutcome,
    RecommendationRule,
    ValidationStatus,
)
from travelops_recovery_agent.application.recommendations import (
    CandidateItinerary,
    RecommendationService,
    validate_recommendation_option,
)
from travelops_recovery_agent.application.services import RecoveryDataUnitOfWorkFactory
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import Flight

NOW = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)


def flight(
    flight_id: str,
    origin: str,
    destination: str,
    departure: datetime,
    arrival: datetime,
) -> Flight:
    return Flight(
        id=flight_id,
        carrier_code="NV",
        flight_number=flight_id.removeprefix("FLT-NV"),
        origin=origin,
        destination=destination,
        scheduled_departure=departure,
        scheduled_arrival=arrival,
    )


def status(
    item: Flight,
    operational_status: OperationalFlightStatus = OperationalFlightStatus.SCHEDULED,
    delay_minutes: int | None = None,
) -> FlightStatus:
    return FlightStatus(
        flight=item,
        status=operational_status,
        delay_minutes=delay_minutes,
        cancellation_reason=(
            "Synthetic cancellation"
            if operational_status is OperationalFlightStatus.CANCELLED
            else None
        ),
        related_disruptions=(),
    )


def availability(item: Flight, seats: int = 4) -> AvailabilityEvidence:
    return AvailabilityEvidence(
        flight_id=item.id,
        available_seats=seats,
        observed_at=NOW,
        source="benchmark:availability",
    )


def ticket(*, allowed: bool = True, connections: int = 1) -> TicketRuleEvidence:
    return TicketRuleEvidence(
        booking_id="BKG-0001",
        rebooking_allowed=allowed,
        allowed_carrier_code="NV",
        max_connections=connections,
        observed_at=NOW,
        source="benchmark:ticket-rule",
    )


def assess(
    flights: tuple[Flight, ...],
    *,
    statuses: dict[str, FlightStatus] | None = None,
    inventory: dict[str, AvailabilityEvidence] | None = None,
    rule: TicketRuleEvidence | bool | None = True,
    passenger_count: int = 2,
) -> RecommendationOption:
    resolved_rule = ticket() if rule is True else rule
    if resolved_rule is False:
        resolved_rule = None
    return validate_recommendation_option(
        CandidateItinerary(tuple(item.id for item in flights)),
        flights_by_id={item.id: item for item in flights},
        statuses_by_id=(
            {item.id: status(item) for item in flights}
            if statuses is None
            else statuses
        ),
        availability_by_id=(
            {item.id: availability(item) for item in flights}
            if inventory is None
            else inventory
        ),
        ticket_rule=resolved_rule,
        passenger_count=passenger_count,
        policy_id="POL-STANDARD",
        policy_allows_next_day=True,
        policy_deadline=NOW + timedelta(days=2),
        disruption_date=NOW,
    )


@pytest.mark.parametrize("connecting", [False, True])
def test_valid_direct_and_connecting_options_pass_every_rule(connecting: bool) -> None:
    first = flight(
        "FLT-NV701",
        "AAA",
        "BBB" if connecting else "CCC",
        NOW,
        NOW + timedelta(hours=2),
    )
    flights: tuple[Flight, ...] = (first,)
    if connecting:
        flights += (
            flight(
                "FLT-NV702",
                "BBB",
                "CCC",
                NOW + timedelta(hours=3),
                NOW + timedelta(hours=5),
            ),
        )

    result = assess(flights)

    assert result.validation.valid
    assert result.validation.evidence_complete
    assert all(
        item.status is ValidationStatus.PASSED for item in result.validation.checks
    )
    assert result.ranking_inputs is not None


def test_invalid_route_overlap_and_minimum_connection_are_explicit() -> None:
    first = flight("FLT-NV711", "AAA", "BBB", NOW, NOW + timedelta(hours=2))
    disconnected = flight(
        "FLT-NV712", "DDD", "CCC", NOW + timedelta(hours=3), NOW + timedelta(hours=5)
    )
    overlapping = flight(
        "FLT-NV713",
        "BBB",
        "CCC",
        NOW + timedelta(hours=1, minutes=30),
        NOW + timedelta(hours=4),
    )
    short = flight(
        "FLT-NV714",
        "BBB",
        "CCC",
        NOW + timedelta(hours=2, minutes=30),
        NOW + timedelta(hours=4),
    )

    route_result = assess((first, disconnected))
    overlap_result = assess((first, overlapping))
    mct_result = assess((first, short))

    checks = {item.rule: item for item in route_result.validation.checks}
    assert checks[RecommendationRule.ROUTE_CONTINUITY].status is ValidationStatus.FAILED
    checks = {item.rule: item for item in overlap_result.validation.checks}
    assert (
        checks[RecommendationRule.FLIGHT_AND_CONNECTION_TIMES].status
        is ValidationStatus.FAILED
    )
    checks = {item.rule: item for item in mct_result.validation.checks}
    assert (
        checks[RecommendationRule.MINIMUM_CONNECTION_TIME].status
        is ValidationStatus.FAILED
    )


def test_complete_group_seats_ticket_rules_and_cancelled_status_can_reject() -> None:
    item = flight("FLT-NV721", "AAA", "CCC", NOW, NOW + timedelta(hours=2))
    seat_result = assess(
        (item,), inventory={item.id: availability(item, 1)}, passenger_count=3
    )
    ticket_result = assess((item,), rule=ticket(allowed=False))
    cancelled_result = assess(
        (item,), statuses={item.id: status(item, OperationalFlightStatus.CANCELLED)}
    )

    assert "complete group of 3" in " ".join(seat_result.validation.rejection_reasons)
    assert "not marked rebookable" in " ".join(
        ticket_result.validation.rejection_reasons
    )
    assert "Cancelled flights" in " ".join(
        cancelled_result.validation.rejection_reasons
    )


def test_missing_flight_status_inventory_and_ticket_evidence_never_pass() -> None:
    item = flight("FLT-NV731", "AAA", "CCC", NOW, NOW + timedelta(hours=2))
    missing_flight = validate_recommendation_option(
        CandidateItinerary(("FLT-NV999",)),
        flights_by_id={},
        statuses_by_id={},
        availability_by_id={},
        ticket_rule=ticket(),
        passenger_count=1,
        policy_id="POL-STANDARD",
        policy_allows_next_day=True,
        policy_deadline=NOW + timedelta(days=1),
        disruption_date=NOW,
    )
    missing_evidence = assess((item,), statuses={}, inventory={}, rule=None)

    assert not missing_flight.validation.valid
    assert "missing" in missing_flight.validation.rejection_reasons[0].lower()
    assert not missing_evidence.validation.valid
    statuses = {check.status for check in missing_evidence.validation.checks}
    assert ValidationStatus.MISSING_EVIDENCE in statuses


class BenchmarkRepository:
    def __init__(
        self,
        *,
        ticket_allowed: bool = True,
        include_inventory: bool = True,
    ) -> None:
        self.dataset = generate_dataset(seed=42)
        self.ticket_allowed = ticket_allowed
        self.include_inventory = include_inventory

    def get_complete_case(self, case_id: str) -> CompleteRecoveryCase | None:
        case = next(item for item in self.dataset.recovery_cases if item.id == case_id)
        booking = next(
            item for item in self.dataset.bookings if item.id == case.booking_id
        )
        disruption = next(
            item for item in self.dataset.disruptions if item.id == case.disruption_id
        )
        flights = {item.id: item for item in self.dataset.flights}
        return CompleteRecoveryCase(
            recovery_case=case,
            booking=booking,
            passengers=tuple(
                item
                for item in self.dataset.passengers
                if item.id in booking.passenger_ids
            ),
            flights=tuple(flights[item.flight_id] for item in booking.segments),
            disruption=disruption,
            policy=self.dataset.policies[0],
        )

    def list_flights_in_window(
        self, earliest_departure: datetime, latest_arrival: datetime
    ) -> tuple[Flight, ...]:
        return tuple(
            item
            for item in self.dataset.flights
            if item.scheduled_departure >= earliest_departure
            and item.scheduled_arrival <= latest_arrival
        )

    def get_flights_by_ids(self, flight_ids: tuple[str, ...]) -> tuple[Flight, ...]:
        return tuple(item for item in self.dataset.flights if item.id in flight_ids)

    def get_flight_with_disruptions(
        self, flight_id: str
    ) -> FlightWithDisruptions | None:
        stored = next(
            (item for item in self.dataset.flights if item.id == flight_id), None
        )
        if stored is None:
            return None
        return FlightWithDisruptions(
            flight=stored,
            disruptions=tuple(
                item
                for item in self.dataset.disruptions
                if item.affected_flight_id == flight_id
            ),
        )

    def get_availability_by_flight_ids(
        self, flight_ids: tuple[str, ...]
    ) -> tuple[AvailabilityEvidence, ...]:
        if not self.include_inventory:
            return ()
        return tuple(
            AvailabilityEvidence(item, 6, NOW, "benchmark:availability")
            for item in flight_ids
        )

    def get_ticket_rule(self, booking_id: str) -> TicketRuleEvidence | None:
        return TicketRuleEvidence(
            booking_id,
            self.ticket_allowed,
            "NV",
            1,
            NOW,
            "benchmark:ticket-rule",
        )


class BenchmarkUnitOfWork:
    def __init__(self, repository: BenchmarkRepository) -> None:
        self.repository = repository

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def recommendation_service(repository: BenchmarkRepository) -> RecommendationService:
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BenchmarkUnitOfWork(repository),
    )
    return RecommendationService(factory)


def test_ranking_is_stable_and_exposes_all_inputs() -> None:
    service = recommendation_service(BenchmarkRepository())

    first = service.recommend("CASE-0001")
    second = service.recommend("CASE-0001")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.outcome is RecommendationOutcome.RECOMMENDED
    assert first.recommended_itinerary is not None
    assert first.recommended_itinerary.ranking_inputs is not None
    assert first.recommended_itinerary.ranking_inputs.rank_position == 1
    assert first.other_validated_options
    assert all(item.validation.valid for item in first.other_validated_options)


def test_no_option_and_insufficient_evidence_are_distinct_escalations() -> None:
    no_option = recommendation_service(
        BenchmarkRepository(ticket_allowed=False)
    ).recommend("CASE-0001")
    insufficient = recommendation_service(
        BenchmarkRepository(include_inventory=False)
    ).recommend("CASE-0001")

    assert no_option.outcome is RecommendationOutcome.NO_SAFE_OPTION
    assert no_option.recommended_itinerary is None
    assert no_option.escalation_reason
    assert insufficient.outcome is RecommendationOutcome.INSUFFICIENT_EVIDENCE
    assert insufficient.recommended_itinerary is None
    assert insufficient.escalation_reason
