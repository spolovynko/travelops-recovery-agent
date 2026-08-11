"""Tests for deterministic synthetic airline data generation."""

import random
from collections import Counter

from travelops_recovery_agent.data.generator import (
    GENERATOR_VERSION,
    generate_dataset,
)
from travelops_recovery_agent.domain.models import (
    DelayedFlightDetails,
    DisruptionType,
)


def test_generator_returns_a_valid_recovery_dataset() -> None:
    dataset = generate_dataset(seed=20260811)

    assert dataset.metadata.generator_version == GENERATOR_VERSION
    assert dataset.metadata.seed == 20260811
    assert len(dataset.passengers) == 13
    assert len(dataset.flights) == 20
    assert len(dataset.bookings) == 10
    assert len(dataset.disruptions) == 10
    assert len(dataset.recovery_cases) == 10
    assert isinstance(dataset.disruptions[0].details, DelayedFlightDetails)


def test_generator_covers_all_required_disruption_types() -> None:
    dataset = generate_dataset(seed=20260811)

    disruption_counts = Counter(
        disruption.details.type for disruption in dataset.disruptions
    )

    assert disruption_counts == {
        DisruptionType.DELAYED_FLIGHT: 3,
        DisruptionType.CANCELLED_FLIGHT: 4,
        DisruptionType.MISSED_CONNECTION: 3,
    }


def test_generator_preserves_reviewed_case_order_and_titles() -> None:
    dataset = generate_dataset(seed=20260811)

    assert [case.id for case in dataset.recovery_cases] == [
        f"CASE-{number:04d}" for number in range(1, 11)
    ]
    assert [case.title for case in dataset.recovery_cases] == [
        "Short delay on originating flight",
        "Long delay on connecting flight",
        "Missed connection after inbound delay",
        "Cancelled originating flight",
        "Cancelled connecting flight",
        "Cancellation close to departure",
        "Group booking affected by cancellation",
        "Missed connection on a two-segment journey",
        "Severe delay before onward connection",
        "Group booking with a missed connection",
    ]


def test_generator_builds_the_reviewed_group_bookings() -> None:
    dataset = generate_dataset(seed=20260811)
    bookings_by_id = {booking.id: booking for booking in dataset.bookings}

    assert len(bookings_by_id["BKG-0007"].passenger_ids) == 3
    assert len(bookings_by_id["BKG-0010"].passenger_ids) == 2


def test_each_case_references_the_matching_numbered_records() -> None:
    dataset = generate_dataset(seed=20260811)

    for number, recovery_case in enumerate(dataset.recovery_cases, start=1):
        suffix = f"{number:04d}"
        assert recovery_case.booking_id == f"BKG-{suffix}"
        assert recovery_case.disruption_id == f"DIS-{suffix}"
        assert recovery_case.policy_id == "POL-STANDARD"


def test_same_seed_produces_equal_datasets() -> None:
    first = generate_dataset(seed=42)
    second = generate_dataset(seed=42)

    assert first == second


def test_same_seed_produces_identical_serialized_bytes() -> None:
    first = generate_dataset(seed=42).model_dump_json(indent=2).encode("utf-8")
    second = generate_dataset(seed=42).model_dump_json(indent=2).encode("utf-8")

    assert first == second


def test_different_seeds_are_recorded_in_different_datasets() -> None:
    first = generate_dataset(seed=41)
    second = generate_dataset(seed=42)

    assert first.metadata.seed == 41
    assert second.metadata.seed == 42
    assert first != second


def test_generator_does_not_mutate_global_random_state() -> None:
    original_state = random.getstate()

    try:
        random.seed(12345)
        expected_next_value = random.random()

        random.seed(12345)
        generate_dataset(seed=42)
        actual_next_value = random.random()
    finally:
        random.setstate(original_state)

    assert actual_next_value == expected_next_value
