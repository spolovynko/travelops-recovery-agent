"""Tests for explicit persistence and domain mapping."""

from datetime import timedelta

import pytest

from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.mapping import (
    PersistenceMappingError,
    booking_from_record,
    booking_to_record,
    disruption_from_record,
    disruption_to_record,
    flight_from_record,
    flight_to_record,
    passenger_from_record,
    passenger_to_record,
    policy_from_record,
    policy_to_record,
    recovery_case_from_record,
    recovery_case_to_record,
)


def test_passenger_and_flight_round_trip_through_records() -> None:
    dataset = generate_dataset(seed=42)

    passenger = dataset.passengers[0]
    flight = dataset.flights[0]

    assert passenger_from_record(passenger_to_record(passenger)) == passenger
    assert flight_from_record(flight_to_record(flight)) == flight


def test_booking_round_trip_preserves_passengers_and_segment_order() -> None:
    booking = generate_dataset(seed=42).bookings[6]

    result = booking_from_record(booking_to_record(booking))

    assert result == booking


def test_every_disruption_type_round_trips_through_typed_columns() -> None:
    dataset = generate_dataset(seed=42)

    for disruption in dataset.disruptions:
        result = disruption_from_record(disruption_to_record(disruption))

        assert result == disruption


def test_policy_round_trip_preserves_ordered_applicable_types() -> None:
    policy = generate_dataset(seed=42).policies[0]

    result = policy_from_record(policy_to_record(policy))

    assert result == policy


def test_recovery_case_round_trips_through_foreign_key_fields() -> None:
    recovery_case = generate_dataset(seed=42).recovery_cases[0]

    result = recovery_case_from_record(recovery_case_to_record(recovery_case))

    assert result == recovery_case


def test_corrupted_flight_record_fails_clearly_at_mapping_boundary() -> None:
    flight = generate_dataset(seed=42).flights[0]
    record = flight_to_record(flight)
    record.scheduled_arrival = record.scheduled_departure - timedelta(minutes=1)

    with pytest.raises(
        PersistenceMappingError,
        match=f"stored flight {flight.id} violates domain invariants",
    ) as error:
        flight_from_record(record)

    assert error.value.__cause__ is not None


def test_corrupted_disruption_detail_columns_fail_at_mapping_boundary() -> None:
    disruption = generate_dataset(seed=42).disruptions[0]
    record = disruption_to_record(disruption)
    record.cancellation_reason = "unexpected extra detail"

    with pytest.raises(
        PersistenceMappingError,
        match=f"stored disruption {disruption.id} violates domain invariants",
    ) as error:
        disruption_from_record(record)

    assert error.value.__cause__ is not None
