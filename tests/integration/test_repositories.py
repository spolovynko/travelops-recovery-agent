"""Real-PostgreSQL tests for the SQLAlchemy recovery repository."""

from datetime import UTC, datetime

import pytest

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.application.query_models import (
    CompleteBooking,
    FlightWithDisruptions,
    ResolvedDisruptionPolicy,
)
from travelops_recovery_agent.application.repositories import RecoveryDataRepository
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.repositories import (
    SqlAlchemyRecoveryDataRepository,
)
from travelops_recovery_agent.persistence.session import SessionFactory


def expected_complete_case(case_index: int) -> CompleteRecoveryCase:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    booking = next(
        item for item in dataset.bookings if item.id == recovery_case.booking_id
    )
    disruption = next(
        item for item in dataset.disruptions if item.id == recovery_case.disruption_id
    )
    policy = next(
        item for item in dataset.policies if item.id == recovery_case.policy_id
    )
    passengers_by_id = {passenger.id: passenger for passenger in dataset.passengers}
    flights_by_id = {flight.id: flight for flight in dataset.flights}

    return CompleteRecoveryCase(
        recovery_case=recovery_case,
        booking=booking,
        passengers=tuple(
            passengers_by_id[passenger_id] for passenger_id in booking.passenger_ids
        ),
        flights=tuple(flights_by_id[segment.flight_id] for segment in booking.segments),
        disruption=disruption,
        policy=policy,
    )


def expected_complete_booking(case_index: int) -> CompleteBooking:
    complete_case = expected_complete_case(case_index)
    return CompleteBooking(
        booking=complete_case.booking,
        passengers=complete_case.passengers,
        flights=complete_case.flights,
    )


@pytest.mark.integration
def test_repository_adds_counts_retrieves_and_clears_dataset(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = generate_dataset(seed=42)

    with clean_session_factory.begin() as session:
        repository: RecoveryDataRepository = SqlAlchemyRecoveryDataRepository(session)
        assert repository.counts().is_empty()
        repository.add_dataset(dataset)

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        assert repository.counts() == PersistenceRecordCounts(
            passengers=13,
            flights=20,
            bookings=10,
            booking_passengers=13,
            itinerary_segments=20,
            disruptions=10,
            disruption_policies=1,
            disruption_policy_types=3,
            recovery_cases=10,
        )
        complete_case = repository.get_complete_case("CASE-0007")

    assert complete_case == expected_complete_case(case_index=6)

    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.clear()
        assert repository.counts().is_empty()


@pytest.mark.integration
def test_repository_lists_complete_cases_in_stable_order(
    clean_session_factory: SessionFactory,
) -> None:
    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        assert repository.list_complete_cases() == ()

    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(generate_dataset(seed=42))

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        complete_cases = repository.list_complete_cases()

    assert [item.recovery_case.id for item in complete_cases] == [
        f"CASE-{case_number:04d}" for case_number in range(1, 11)
    ]
    assert complete_cases == tuple(
        expected_complete_case(case_index) for case_index in range(10)
    )


@pytest.mark.integration
def test_repository_writes_roll_back_with_the_callers_transaction(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = generate_dataset(seed=42)

    with (
        pytest.raises(RuntimeError, match="simulated service failure"),
        clean_session_factory.begin() as session,
    ):
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(dataset)
        raise RuntimeError("simulated service failure")

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        assert repository.counts().is_empty()


@pytest.mark.integration
def test_repository_retrieves_a_complete_booking_without_persistence_records(
    clean_session_factory: SessionFactory,
) -> None:
    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(generate_dataset(seed=42))

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        complete_booking = repository.get_complete_booking("BKG-0007")
        missing_booking = repository.get_complete_booking("BKG-9999")

    assert complete_booking == expected_complete_booking(case_index=6)
    assert missing_booking is None


@pytest.mark.integration
def test_repository_retrieves_flight_with_ordered_disruption_evidence(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = generate_dataset(seed=42)
    expected_flight = next(item for item in dataset.flights if item.id == "FLT-NV101")
    expected_disruption = next(
        item for item in dataset.disruptions if item.id == "DIS-0001"
    )

    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(dataset)

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        result = repository.get_flight_with_disruptions("FLT-NV101")
        missing = repository.get_flight_with_disruptions("FLT-NV999")

    assert result == FlightWithDisruptions(
        flight=expected_flight,
        disruptions=(expected_disruption,),
    )
    assert missing is None


@pytest.mark.integration
def test_repository_resolves_policy_by_case_or_disruption(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = generate_dataset(seed=42)
    expected = ResolvedDisruptionPolicy(
        recovery_case=dataset.recovery_cases[0],
        disruption=dataset.disruptions[0],
        policy=dataset.policies[0],
    )

    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(dataset)

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        by_case = repository.get_disruption_policy_for_case("CASE-0001")
        by_disruption = repository.get_disruption_policy_for_disruption("DIS-0001")
        missing = repository.get_disruption_policy_for_disruption("DIS-9999")

    assert by_case == expected
    assert by_disruption == expected
    assert missing is None


@pytest.mark.integration
def test_repository_lists_flights_in_a_bounded_window_deterministically(
    clean_session_factory: SessionFactory,
) -> None:
    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(generate_dataset(seed=42))

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        flights = repository.list_flights_in_window(
            datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            datetime(2026, 1, 15, 18, 0, tzinfo=UTC),
        )

    assert [flight.id for flight in flights] == ["FLT-NV101", "FLT-NV102"]


@pytest.mark.integration
def test_repository_retrieves_only_explicit_flight_identifiers(
    clean_session_factory: SessionFactory,
) -> None:
    with clean_session_factory.begin() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        repository.add_dataset(generate_dataset(seed=42))

    with clean_session_factory() as session:
        repository = SqlAlchemyRecoveryDataRepository(session)
        flights = repository.get_flights_by_ids(("FLT-NV102", "FLT-NV101"))
        partial = repository.get_flights_by_ids(("FLT-NV101", "FLT-MISSING"))

    assert [flight.id for flight in flights] == ["FLT-NV101", "FLT-NV102"]
    assert [flight.id for flight in partial] == ["FLT-NV101"]
