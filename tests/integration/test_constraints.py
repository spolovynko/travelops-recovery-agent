"""Real-PostgreSQL tests for important database constraints."""

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.models import (
    BookingPassengerRecord,
    DisruptionRecord,
    FlightAvailabilityEvidenceRecord,
    ItinerarySegmentRecord,
    PassengerRecord,
    RecoveryCaseRecord,
    TicketRuleEvidenceRecord,
)
from travelops_recovery_agent.persistence.repositories import (
    SqlAlchemyRecoveryDataRepository,
)
from travelops_recovery_agent.persistence.session import SessionFactory


def seed_database(session_factory: SessionFactory) -> SyntheticDataset:
    dataset = generate_dataset(seed=42)
    with session_factory.begin() as session:
        SqlAlchemyRecoveryDataRepository(session).add_dataset(dataset)
    return dataset


@pytest.mark.integration
def test_duplicate_stable_identifier_is_rejected(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = seed_database(clean_session_factory)
    passenger = dataset.passengers[0]

    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            PassengerRecord(
                id=passenger.id,
                given_name="Duplicate",
                family_name="Passenger",
            )
        )
        session.flush()


@pytest.mark.integration
def test_booking_passenger_requires_existing_records(
    clean_session_factory: SessionFactory,
) -> None:
    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            BookingPassengerRecord(
                booking_id="BOOKING-MISSING",
                passenger_id="PAX-MISSING",
            )
        )
        session.flush()


@pytest.mark.integration
def test_segment_sequence_must_be_unique_within_booking(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = seed_database(clean_session_factory)
    booking = dataset.bookings[0]
    existing_flight_ids = {segment.flight_id for segment in booking.segments}
    unused_flight = next(
        flight for flight in dataset.flights if flight.id not in existing_flight_ids
    )

    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            ItinerarySegmentRecord(
                id="SEGMENT-DUPLICATE-SEQUENCE",
                booking_id=booking.id,
                flight_id=unused_flight.id,
                sequence=booking.segments[0].sequence,
            )
        )
        session.flush()


@pytest.mark.integration
def test_disruption_segment_and_flight_must_agree(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = seed_database(clean_session_factory)
    segment = dataset.bookings[0].segments[0]
    different_flight = next(
        flight for flight in dataset.flights if flight.id != segment.flight_id
    )

    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            DisruptionRecord(
                id="DISRUPTION-MISMATCH",
                affected_flight_id=different_flight.id,
                affected_segment_id=segment.id,
                occurred_at=dataset.disruptions[0].occurred_at,
                type="delayed_flight",
                delay_minutes=15,
            )
        )
        session.flush()


@pytest.mark.integration
def test_disruption_type_specific_details_are_enforced(
    clean_session_factory: SessionFactory,
) -> None:
    dataset = seed_database(clean_session_factory)
    segment = dataset.bookings[0].segments[0]

    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            DisruptionRecord(
                id="DISRUPTION-MISSING-DETAILS",
                affected_flight_id=segment.flight_id,
                affected_segment_id=segment.id,
                occurred_at=dataset.disruptions[0].occurred_at,
                type="delayed_flight",
                delay_minutes=None,
            )
        )
        session.flush()


@pytest.mark.integration
def test_recovery_case_requires_existing_related_records(
    clean_session_factory: SessionFactory,
) -> None:
    with (
        pytest.raises(IntegrityError),
        clean_session_factory.begin() as session,
    ):
        session.add(
            RecoveryCaseRecord(
                id="CASE-MISSING-RELATIONSHIPS",
                title="Invalid synthetic case",
                booking_id="BOOKING-MISSING",
                disruption_id="DISRUPTION-MISSING",
                policy_id="POLICY-MISSING",
            )
        )
        session.flush()


@pytest.mark.integration
def test_recommendation_evidence_constraints_reject_unsafe_values(
    clean_session_factory: SessionFactory,
) -> None:
    seed_database(clean_session_factory)

    with pytest.raises(IntegrityError), clean_session_factory.begin() as session:
        session.execute(
            update(FlightAvailabilityEvidenceRecord)
            .where(FlightAvailabilityEvidenceRecord.flight_id == "FLT-NV1003")
            .values(available_seats=-1)
        )
        session.flush()

    with pytest.raises(IntegrityError), clean_session_factory.begin() as session:
        session.execute(
            update(TicketRuleEvidenceRecord)
            .where(TicketRuleEvidenceRecord.booking_id == "BKG-0001")
            .values(max_connections=5)
        )
        session.flush()
