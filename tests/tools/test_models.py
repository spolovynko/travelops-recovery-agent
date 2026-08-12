"""Schema tests for operational-tool inputs and outputs."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.domain.models import DisruptionType
from travelops_recovery_agent.tools.models import (
    BookingItinerarySegment,
    BookingPassenger,
    FlightOperationalStatus,
    FlightStatusDisruption,
    GetBookingInput,
    GetBookingOutput,
    GetDisruptionPolicyInput,
    GetDisruptionPolicyOutput,
    GetFlightStatusInput,
    GetFlightStatusOutput,
)


def test_get_booking_input_publishes_a_strict_stable_schema() -> None:
    schema = GetBookingInput.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["booking_id"]
    assert schema["properties"]["booking_id"]["pattern"] == r"^BKG-[A-Z0-9]+$"


@pytest.mark.parametrize(
    "booking_id",
    ["", "BKG-", "bkg-0001", "DROP TABLE bookings"],
)
def test_get_booking_input_rejects_malformed_identifiers(booking_id: str) -> None:
    with pytest.raises(ValidationError, match="booking_id"):
        GetBookingInput(booking_id=booking_id)


def test_get_booking_output_is_structured_and_minimizes_passenger_data() -> None:
    output = GetBookingOutput(
        booking_id="BKG-0001",
        passengers=(
            BookingPassenger(
                passenger_id="PAX-0001",
                display_name="Mina Vale",
            ),
        ),
        itinerary=(
            BookingItinerarySegment(
                segment_id="SEG-0011",
                sequence=1,
                flight_id="FLT-NV101",
                carrier_code="NV",
                flight_number="101",
                origin="ZRA",
                destination="QVB",
                scheduled_departure=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                scheduled_arrival=datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
            ),
        ),
    )

    payload = output.model_dump(mode="json")
    assert payload["passengers"] == [
        {"passenger_id": "PAX-0001", "display_name": "Mina Vale"}
    ]
    assert "given_name" not in output.model_dump_json()
    assert "family_name" not in output.model_dump_json()
    assert output.itinerary[0].sequence == 1


def test_get_booking_output_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="email"):
        BookingPassenger.model_validate(
            {
                "passenger_id": "PAX-0001",
                "display_name": "Mina Vale",
                "email": "not-required@example.invalid",
            }
        )


def test_get_flight_status_input_publishes_a_strict_stable_schema() -> None:
    schema = GetFlightStatusInput.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["flight_id"]
    assert schema["properties"]["flight_id"]["pattern"] == r"^FLT-[A-Z0-9]+$"


def test_get_flight_status_output_is_structured_synthetic_status_data() -> None:
    output = GetFlightStatusOutput(
        flight_id="FLT-NV101",
        carrier_code="NV",
        flight_number="101",
        origin="ZRA",
        destination="QVB",
        scheduled_departure=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        scheduled_arrival=datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
        operational_status=FlightOperationalStatus.DELAYED,
        delay_minutes=30,
        cancellation_reason=None,
        related_disruptions=(
            FlightStatusDisruption(
                disruption_id="DIS-0001",
                disruption_type=DisruptionType.DELAYED_FLIGHT,
                occurred_at=datetime(2026, 1, 15, 11, 0, tzinfo=UTC),
            ),
        ),
        source="synthetic_dataset",
    )

    assert output.operational_status is FlightOperationalStatus.DELAYED
    assert output.source == "synthetic_dataset"
    assert "estimated_departure" not in output.model_dump_json()


@pytest.mark.parametrize("flight_id", ["", "FLT-", "flt-NV101", "NV101"])
def test_get_flight_status_input_rejects_malformed_identifiers(flight_id: str) -> None:
    with pytest.raises(ValidationError, match="flight_id"):
        GetFlightStatusInput(flight_id=flight_id)


@pytest.mark.parametrize(
    "payload",
    [
        {"reference": {"type": "recovery_case", "id": "CASE-0001"}},
        {"reference": {"type": "disruption", "id": "DIS-0001"}},
    ],
)
def test_get_disruption_policy_accepts_one_explicit_typed_reference(
    payload: dict[str, object],
) -> None:
    tool_input = GetDisruptionPolicyInput.model_validate(payload)

    assert tool_input.reference.id in {"CASE-0001", "DIS-0001"}


@pytest.mark.parametrize(
    "payload",
    [
        {"reference": {"type": "recovery_case", "id": "DIS-0001"}},
        {"reference": {"type": "disruption", "id": "CASE-0001"}},
        {"reference": {"type": "unknown", "id": "CASE-0001"}},
        {},
    ],
)
def test_get_disruption_policy_rejects_malformed_or_ambiguous_references(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        GetDisruptionPolicyInput.model_validate(payload)


def test_get_disruption_policy_output_contains_structured_policy_facts() -> None:
    output = GetDisruptionPolicyOutput(
        resolved_via="recovery_case",
        recovery_case_id="CASE-0001",
        disruption_id="DIS-0001",
        disruption_type=DisruptionType.DELAYED_FLIGHT,
        affected_flight_id="FLT-NV101",
        policy_id="POL-STANDARD",
        name="Synthetic standard recovery",
        summary="Permit recovery after supported fictional disruptions.",
        applicable_types=(
            DisruptionType.DELAYED_FLIGHT,
            DisruptionType.CANCELLED_FLIGHT,
            DisruptionType.MISSED_CONNECTION,
        ),
        rebooking_window_hours=24,
        allows_next_day=True,
    )

    assert output.rebooking_window_hours == 24
    assert output.allows_next_day is True
    assert "prompt" not in output.model_dump_json().lower()
