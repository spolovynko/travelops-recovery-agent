"""Tests for the direct no-LLM operational-tool runner."""

import json
from typing import cast

import pytest

from travelops_recovery_agent.application.query_models import CompleteBooking
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import BookingId
from travelops_recovery_agent.tools.adapters import (
    GetBookingTool,
    GetDisruptionPolicyTool,
    GetFlightStatusTool,
    SearchAlternativeItinerariesTool,
    ValidateItineraryTool,
)
from travelops_recovery_agent.tools.cli import ToolRuntime, main


class BookingServiceStub:
    def __init__(self, result: CompleteBooking | None) -> None:
        self.result = result

    def get_booking(self, booking_id: BookingId) -> CompleteBooking | None:
        return self.result


def complete_booking() -> CompleteBooking:
    dataset = generate_dataset(seed=42)
    booking = dataset.bookings[6]
    passengers = {item.id: item for item in dataset.passengers}
    flights = {item.id: item for item in dataset.flights}
    return CompleteBooking(
        booking=booking,
        passengers=tuple(passengers[item] for item in booking.passenger_ids),
        flights=tuple(flights[item.flight_id] for item in booking.segments),
    )


def runtime(result: CompleteBooking | None) -> ToolRuntime:
    service = cast(OperationalQueryService, BookingServiceStub(result))
    return ToolRuntime(
        get_booking=GetBookingTool(service),
        get_flight_status=GetFlightStatusTool(service),
        get_disruption_policy=GetDisruptionPolicyTool(service),
        search_alternative_itineraries=SearchAlternativeItinerariesTool(service),
        validate_itinerary=ValidateItineraryTool(service),
    )


def test_catalog_prints_all_schemas_without_database_configuration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["catalog"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert [item["name"] for item in payload] == [
        "get_booking",
        "get_flight_status",
        "get_disruption_policy",
        "search_alternative_itineraries",
        "validate_itinerary",
    ]


def test_cli_invokes_a_guarded_tool_and_prints_structured_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--actor-id",
            "operator-17",
            "--correlation-id",
            "manual-test-1",
            "get-booking",
            "BKG-0007",
        ],
        runtime=runtime(complete_booking()),
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["booking_id"] == "BKG-0007"
    assert payload["audit"]["actor_id"] == "operator-17"


def test_cli_returns_nonzero_for_a_typed_tool_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["get-booking", "BKG-9999"],
        runtime=runtime(None),
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
