"""Real-PostgreSQL tests for the SQLAlchemy recovery repository."""

import pytest

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
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
