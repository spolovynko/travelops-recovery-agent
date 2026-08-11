"""Tests for core airline domain models and invariants."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.domain.models import (
    Booking,
    CancelledFlightDetails,
    DelayedFlightDetails,
    Disruption,
    DisruptionPolicy,
    DisruptionType,
    Flight,
    ItinerarySegment,
    MissedConnectionDetails,
    Passenger,
    RecoveryCase,
    validate_itinerary,
)


def valid_flight_data() -> dict[str, object]:
    return {
        "id": "FLT-NV101",
        "carrier_code": "NV",
        "flight_number": "101",
        "origin": "NRV",
        "destination": "VLY",
        "scheduled_departure": datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
        "scheduled_arrival": datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
    }


def valid_booking_data() -> dict[str, object]:
    return {
        "id": "BKG-0001",
        "passenger_ids": ["PAX-0001"],
        "segments": [
            {"id": "SEG-0001", "flight_id": "FLT-NV101", "sequence": 1},
            {"id": "SEG-0002", "flight_id": "FLT-NV202", "sequence": 2},
        ],
    }


def test_passenger_accepts_a_stable_identifier_and_normalizes_names() -> None:
    passenger = Passenger(
        id="PAX-0001",
        given_name="  Mina ",
        family_name=" Vale ",
    )

    assert passenger.id == "PAX-0001"
    assert passenger.given_name == "Mina"
    assert passenger.family_name == "Vale"


@pytest.mark.parametrize("passenger_id", ["", "0001", "pax-0001", "PAX-"])
def test_passenger_rejects_invalid_identifiers(passenger_id: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        Passenger(id=passenger_id, given_name="Mina", family_name="Vale")


def test_flight_accepts_a_valid_timezone_aware_schedule() -> None:
    flight = Flight.model_validate(valid_flight_data())

    assert flight.origin == "NRV"
    assert flight.destination == "VLY"
    assert flight.scheduled_departure.tzinfo is UTC


@pytest.mark.parametrize("field", ["scheduled_departure", "scheduled_arrival"])
def test_flight_rejects_naive_datetimes(field: str) -> None:
    flight_data = valid_flight_data()
    flight_data[field] = datetime(2026, 1, 15, 8, 0)

    with pytest.raises(ValidationError, match="datetime must be timezone-aware"):
        Flight.model_validate(flight_data)


def test_flight_rejects_arrival_at_or_before_departure() -> None:
    flight_data = valid_flight_data()
    flight_data["scheduled_arrival"] = flight_data["scheduled_departure"]

    with pytest.raises(
        ValidationError,
        match="scheduled_arrival must be after scheduled_departure",
    ):
        Flight.model_validate(flight_data)


def test_flight_rejects_a_route_that_returns_to_its_origin() -> None:
    flight_data = valid_flight_data()
    flight_data["destination"] = flight_data["origin"]

    with pytest.raises(ValidationError, match="origin and destination must differ"):
        Flight.model_validate(flight_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "NV101"),
        ("carrier_code", "nova"),
        ("flight_number", "01"),
        ("origin", "NV"),
        ("destination", "vale"),
    ],
)
def test_flight_rejects_invalid_codes(field: str, value: str) -> None:
    flight_data = valid_flight_data()
    flight_data[field] = value

    with pytest.raises(ValidationError, match=field):
        Flight.model_validate(flight_data)


def test_domain_models_reject_unknown_fields() -> None:
    flight_data = valid_flight_data()
    flight_data["aircraft_registration"] = "FICT-001"

    with pytest.raises(ValidationError, match="aircraft_registration"):
        Flight.model_validate(flight_data)


def test_booking_accepts_ordered_unique_relationships() -> None:
    booking = Booking.model_validate(valid_booking_data())

    assert booking.passenger_ids == ("PAX-0001",)
    assert booking.segments == (
        ItinerarySegment(id="SEG-0001", flight_id="FLT-NV101", sequence=1),
        ItinerarySegment(id="SEG-0002", flight_id="FLT-NV202", sequence=2),
    )


def test_booking_rejects_an_empty_passenger_list() -> None:
    booking_data = valid_booking_data()
    booking_data["passenger_ids"] = []

    with pytest.raises(
        ValidationError,
        match="booking must contain at least one passenger",
    ):
        Booking.model_validate(booking_data)


def test_booking_rejects_duplicate_passenger_references() -> None:
    booking_data = valid_booking_data()
    booking_data["passenger_ids"] = ["PAX-0001", "PAX-0001"]

    with pytest.raises(
        ValidationError,
        match="booking passenger identifiers must be unique",
    ):
        Booking.model_validate(booking_data)


def test_booking_rejects_an_empty_itinerary() -> None:
    booking_data = valid_booking_data()
    booking_data["segments"] = []

    with pytest.raises(
        ValidationError,
        match="booking must contain at least one segment",
    ):
        Booking.model_validate(booking_data)


def test_booking_rejects_duplicate_segment_identifiers() -> None:
    booking_data = valid_booking_data()
    booking_data["segments"] = [
        {"id": "SEG-0001", "flight_id": "FLT-NV101", "sequence": 1},
        {"id": "SEG-0001", "flight_id": "FLT-NV202", "sequence": 2},
    ]

    with pytest.raises(
        ValidationError,
        match="booking segment identifiers must be unique",
    ):
        Booking.model_validate(booking_data)


def test_booking_rejects_duplicate_flight_references() -> None:
    booking_data = valid_booking_data()
    booking_data["segments"] = [
        {"id": "SEG-0001", "flight_id": "FLT-NV101", "sequence": 1},
        {"id": "SEG-0002", "flight_id": "FLT-NV101", "sequence": 2},
    ]

    with pytest.raises(
        ValidationError,
        match="booking flight identifiers must be unique",
    ):
        Booking.model_validate(booking_data)


@pytest.mark.parametrize(
    "sequences",
    [
        [2, 1],
        [1, 3],
    ],
)
def test_booking_rejects_unordered_or_non_contiguous_segments(
    sequences: list[int],
) -> None:
    booking_data = valid_booking_data()
    booking_data["segments"] = [
        {"id": "SEG-0001", "flight_id": "FLT-NV101", "sequence": sequences[0]},
        {"id": "SEG-0002", "flight_id": "FLT-NV202", "sequence": sequences[1]},
    ]

    with pytest.raises(
        ValidationError,
        match="segment sequence must be ordered and contiguous starting at 1",
    ):
        Booking.model_validate(booking_data)


def connecting_flight_data() -> dict[str, object]:
    return {
        "id": "FLT-NV202",
        "carrier_code": "NV",
        "flight_number": "202",
        "origin": "VLY",
        "destination": "SKY",
        "scheduled_departure": datetime(2026, 1, 15, 12, 30, tzinfo=UTC),
        "scheduled_arrival": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
    }


def test_itinerary_accepts_existing_connected_flights() -> None:
    booking = Booking.model_validate(valid_booking_data())
    first_flight = Flight.model_validate(valid_flight_data())
    second_flight = Flight.model_validate(connecting_flight_data())

    validate_itinerary(
        booking,
        {first_flight.id: first_flight, second_flight.id: second_flight},
    )


def test_itinerary_compares_connection_times_across_timezones() -> None:
    booking = Booking.model_validate(valid_booking_data())
    first_flight = Flight.model_validate(valid_flight_data())
    second_data = connecting_flight_data()
    plus_two = timezone(timedelta(hours=2))
    second_data["scheduled_departure"] = datetime(
        2026,
        1,
        15,
        12,
        30,
        tzinfo=plus_two,
    )
    second_data["scheduled_arrival"] = datetime(
        2026,
        1,
        15,
        14,
        0,
        tzinfo=plus_two,
    )
    second_flight = Flight.model_validate(second_data)

    validate_itinerary(
        booking,
        {first_flight.id: first_flight, second_flight.id: second_flight},
    )


def test_itinerary_rejects_a_missing_flight_reference() -> None:
    booking = Booking.model_validate(valid_booking_data())
    first_flight = Flight.model_validate(valid_flight_data())

    with pytest.raises(
        ValueError,
        match=("booking BKG-0001 segment SEG-0002 references missing flight FLT-NV202"),
    ):
        validate_itinerary(booking, {first_flight.id: first_flight})


def test_itinerary_rejects_broken_geographical_continuity() -> None:
    booking = Booking.model_validate(valid_booking_data())
    first_flight = Flight.model_validate(valid_flight_data())
    second_data = connecting_flight_data()
    second_data["origin"] = "SUN"
    second_flight = Flight.model_validate(second_data)

    with pytest.raises(ValueError, match="itinerary is geographically disconnected"):
        validate_itinerary(
            booking,
            {first_flight.id: first_flight, second_flight.id: second_flight},
        )


def test_itinerary_rejects_a_negative_connection_time() -> None:
    booking = Booking.model_validate(valid_booking_data())
    first_flight = Flight.model_validate(valid_flight_data())
    second_data = connecting_flight_data()
    second_data["scheduled_departure"] = datetime(
        2026,
        1,
        15,
        9,
        30,
        tzinfo=UTC,
    )
    second_data["scheduled_arrival"] = datetime(
        2026,
        1,
        15,
        11,
        0,
        tzinfo=UTC,
    )
    second_flight = Flight.model_validate(second_data)

    with pytest.raises(ValueError, match="itinerary has a negative connection time"):
        validate_itinerary(
            booking,
            {first_flight.id: first_flight, second_flight.id: second_flight},
        )


def valid_disruption_data() -> dict[str, object]:
    return {
        "id": "DIS-0001",
        "affected_flight_id": "FLT-NV101",
        "affected_segment_id": "SEG-0001",
        "occurred_at": datetime(2026, 1, 15, 7, 30, tzinfo=UTC),
        "details": {"type": "delayed_flight", "delay_minutes": 45},
    }


def test_disruption_selects_delayed_details_from_its_type() -> None:
    disruption = Disruption.model_validate(valid_disruption_data())

    assert disruption.details == DelayedFlightDetails(delay_minutes=45)
    assert disruption.details.type is DisruptionType.DELAYED_FLIGHT


def test_disruption_selects_cancelled_details_from_its_type() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["details"] = {
        "type": "cancelled_flight",
        "reason": "Synthetic crew availability issue",
    }

    disruption = Disruption.model_validate(disruption_data)

    assert disruption.details == CancelledFlightDetails(
        reason="Synthetic crew availability issue"
    )


def test_disruption_selects_missed_connection_details_from_its_type() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["affected_flight_id"] = "FLT-NV202"
    disruption_data["affected_segment_id"] = "SEG-0002"
    disruption_data["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV101",
        "missed_flight_id": "FLT-NV202",
    }

    disruption = Disruption.model_validate(disruption_data)

    assert disruption.details == MissedConnectionDetails(
        arriving_flight_id="FLT-NV101",
        missed_flight_id="FLT-NV202",
    )


def test_delayed_disruption_requires_a_positive_delay() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["details"] = {
        "type": "delayed_flight",
        "delay_minutes": 0,
    }

    with pytest.raises(ValidationError, match="delay_minutes"):
        Disruption.model_validate(disruption_data)


def test_disruption_rejects_details_that_do_not_match_its_type() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["details"] = {
        "type": "cancelled_flight",
        "delay_minutes": 45,
    }

    with pytest.raises(ValidationError, match="reason"):
        Disruption.model_validate(disruption_data)


def test_disruption_rejects_a_naive_occurrence_time() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["occurred_at"] = datetime(2026, 1, 15, 7, 30)

    with pytest.raises(ValidationError, match="occurred_at must be timezone-aware"):
        Disruption.model_validate(disruption_data)


def test_missed_connection_requires_two_different_flights() -> None:
    with pytest.raises(
        ValidationError,
        match="arriving and missed flight identifiers must differ",
    ):
        MissedConnectionDetails(
            arriving_flight_id="FLT-NV101",
            missed_flight_id="FLT-NV101",
        )


def test_missed_connection_must_affect_the_missed_flight() -> None:
    disruption_data = valid_disruption_data()
    disruption_data["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV303",
        "missed_flight_id": "FLT-NV202",
    }

    with pytest.raises(
        ValidationError,
        match="a missed connection must affect the missed flight",
    ):
        Disruption.model_validate(disruption_data)


def valid_policy_data() -> dict[str, object]:
    return {
        "id": "POL-STANDARD",
        "name": "Synthetic standard recovery",
        "summary": "Permit rebooking after supported fictional disruptions.",
        "applicable_types": [
            "delayed_flight",
            "cancelled_flight",
            "missed_connection",
        ],
        "rebooking_window_hours": 24,
        "allows_next_day": True,
    }


def test_policy_accepts_unique_applicable_disruption_types() -> None:
    policy = DisruptionPolicy.model_validate(valid_policy_data())

    assert policy.applicable_types == (
        DisruptionType.DELAYED_FLIGHT,
        DisruptionType.CANCELLED_FLIGHT,
        DisruptionType.MISSED_CONNECTION,
    )


def test_policy_requires_an_applicable_disruption_type() -> None:
    policy_data = valid_policy_data()
    policy_data["applicable_types"] = []

    with pytest.raises(
        ValidationError,
        match="policy must apply to at least one disruption type",
    ):
        DisruptionPolicy.model_validate(policy_data)


def test_policy_rejects_duplicate_disruption_types() -> None:
    policy_data = valid_policy_data()
    policy_data["applicable_types"] = ["delayed_flight", "delayed_flight"]

    with pytest.raises(
        ValidationError,
        match="policy disruption types must be unique",
    ):
        DisruptionPolicy.model_validate(policy_data)


def test_recovery_case_holds_explicit_relationship_identifiers() -> None:
    recovery_case = RecoveryCase(
        id="CASE-0001",
        title="Synthetic delayed connection",
        booking_id="BKG-0001",
        disruption_id="DIS-0001",
        policy_id="POL-STANDARD",
    )

    assert recovery_case.booking_id == "BKG-0001"
    assert recovery_case.disruption_id == "DIS-0001"
    assert recovery_case.policy_id == "POL-STANDARD"
