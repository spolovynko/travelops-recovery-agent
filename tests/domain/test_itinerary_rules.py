"""Tests for deterministic candidate-itinerary validation rules."""

from datetime import timedelta

from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRule,
    RuleStatus,
    validate_candidate_itinerary,
)
from travelops_recovery_agent.domain.models import Flight


def test_validation_passes_connected_chronological_stored_flights() -> None:
    flights = generate_dataset(seed=42).flights[:2]

    result = validate_candidate_itinerary(
        tuple(flight.id for flight in flights),
        {flight.id: flight for flight in flights},
    )

    assert result.valid is True
    assert [rule.status for rule in result.rules] == [
        RuleStatus.PASSED,
        RuleStatus.PASSED,
        RuleStatus.PASSED,
    ]


def test_validation_reports_missing_flights_and_skips_dependent_rules() -> None:
    result = validate_candidate_itinerary(("FLT-MISSING",), {})

    assert result.valid is False
    assert result.rules[0].rule is ItineraryRule.FLIGHTS_EXIST
    assert result.rules[0].status is RuleStatus.FAILED
    assert [rule.status for rule in result.rules[1:]] == [
        RuleStatus.NOT_EVALUATED,
        RuleStatus.NOT_EVALUATED,
    ]


def test_validation_rejects_a_disconnected_route() -> None:
    dataset = generate_dataset(seed=42)
    flights = (dataset.flights[0], dataset.flights[3])

    result = validate_candidate_itinerary(
        tuple(flight.id for flight in flights),
        {flight.id: flight for flight in flights},
    )

    assert result.valid is False
    assert result.rules[1].status is RuleStatus.FAILED
    assert result.rules[2].status is RuleStatus.PASSED


def test_validation_rejects_chronologically_overlapping_flights() -> None:
    first = generate_dataset(seed=42).flights[0]
    second = Flight(
        id="FLT-OVERLAP",
        carrier_code="NV",
        flight_number="999",
        origin=first.destination,
        destination="XLC",
        scheduled_departure=first.scheduled_arrival - timedelta(minutes=30),
        scheduled_arrival=first.scheduled_arrival + timedelta(hours=1),
    )

    result = validate_candidate_itinerary(
        (first.id, second.id),
        {first.id: first, second.id: second},
    )

    assert result.valid is False
    assert result.rules[1].status is RuleStatus.PASSED
    assert result.rules[2].status is RuleStatus.FAILED
