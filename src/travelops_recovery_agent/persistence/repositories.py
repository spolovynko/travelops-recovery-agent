"""SQLAlchemy implementation of the recovery data repository."""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.domain.models import RecoveryCaseId
from travelops_recovery_agent.persistence.mapping import (
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
from travelops_recovery_agent.persistence.models import (
    BookingPassengerRecord,
    BookingRecord,
    DisruptionPolicyRecord,
    DisruptionPolicyTypeRecord,
    DisruptionRecord,
    FlightRecord,
    ItinerarySegmentRecord,
    PassengerRecord,
    RecoveryCaseRecord,
)


class SqlAlchemyRecoveryDataRepository:
    """Store and retrieve recovery data using one caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def counts(self) -> PersistenceRecordCounts:
        return PersistenceRecordCounts(
            passengers=int(
                self._session.scalar(select(func.count(PassengerRecord.id))) or 0
            ),
            flights=int(self._session.scalar(select(func.count(FlightRecord.id))) or 0),
            bookings=int(
                self._session.scalar(select(func.count(BookingRecord.id))) or 0
            ),
            booking_passengers=int(
                self._session.scalar(
                    select(func.count(BookingPassengerRecord.booking_id))
                )
                or 0
            ),
            itinerary_segments=int(
                self._session.scalar(select(func.count(ItinerarySegmentRecord.id))) or 0
            ),
            disruptions=int(
                self._session.scalar(select(func.count(DisruptionRecord.id))) or 0
            ),
            disruption_policies=int(
                self._session.scalar(select(func.count(DisruptionPolicyRecord.id))) or 0
            ),
            disruption_policy_types=int(
                self._session.scalar(
                    select(func.count(DisruptionPolicyTypeRecord.policy_id))
                )
                or 0
            ),
            recovery_cases=int(
                self._session.scalar(select(func.count(RecoveryCaseRecord.id))) or 0
            ),
        )

    def add_dataset(self, dataset: SyntheticDataset) -> None:
        self._session.add_all(
            passenger_to_record(passenger) for passenger in dataset.passengers
        )
        self._session.add_all(flight_to_record(flight) for flight in dataset.flights)
        self._session.add_all(policy_to_record(policy) for policy in dataset.policies)
        self._session.flush()

        self._session.add_all(
            booking_to_record(booking) for booking in dataset.bookings
        )
        self._session.flush()

        self._session.add_all(
            disruption_to_record(disruption) for disruption in dataset.disruptions
        )
        self._session.flush()

        self._session.add_all(
            recovery_case_to_record(recovery_case)
            for recovery_case in dataset.recovery_cases
        )
        self._session.flush()

    def get_complete_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        statement = (
            select(RecoveryCaseRecord)
            .where(RecoveryCaseRecord.id == case_id)
            .options(
                joinedload(RecoveryCaseRecord.booking)
                .selectinload(BookingRecord.passenger_links)
                .joinedload(BookingPassengerRecord.passenger),
                joinedload(RecoveryCaseRecord.booking)
                .selectinload(BookingRecord.segments)
                .joinedload(ItinerarySegmentRecord.flight),
                joinedload(RecoveryCaseRecord.disruption),
                joinedload(RecoveryCaseRecord.policy).selectinload(
                    DisruptionPolicyRecord.type_links
                ),
            )
        )

        record = self._session.execute(statement).unique().scalar_one_or_none()
        if record is None:
            return None

        return CompleteRecoveryCase(
            recovery_case=recovery_case_from_record(record),
            booking=booking_from_record(record.booking),
            passengers=tuple(
                passenger_from_record(link.passenger)
                for link in record.booking.passenger_links
            ),
            flights=tuple(
                flight_from_record(segment.flight)
                for segment in record.booking.segments
            ),
            disruption=disruption_from_record(record.disruption),
            policy=policy_from_record(record.policy),
        )

    def clear(self) -> None:
        self._session.execute(delete(RecoveryCaseRecord))
        self._session.execute(delete(DisruptionRecord))
        self._session.execute(delete(BookingRecord))
        self._session.execute(delete(DisruptionPolicyRecord))
        self._session.execute(delete(FlightRecord))
        self._session.execute(delete(PassengerRecord))
        self._session.flush()
