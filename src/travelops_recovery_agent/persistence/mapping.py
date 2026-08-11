"""Explicit mapping between persistence records and domain models."""

from pydantic import BaseModel, ValidationError

from travelops_recovery_agent.domain.models import (
    Booking,
    CancelledFlightDetails,
    DelayedFlightDetails,
    Disruption,
    DisruptionPolicy,
    Flight,
    MissedConnectionDetails,
    Passenger,
    RecoveryCase,
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


class PersistenceMappingError(ValueError):
    """Raised when a stored record violates domain invariants."""


def _validate_domain[DomainT: BaseModel](
    model_type: type[DomainT],
    payload: object,
    *,
    entity_name: str,
    entity_id: str,
) -> DomainT:
    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        raise PersistenceMappingError(
            f"stored {entity_name} {entity_id} violates domain invariants"
        ) from error


def passenger_to_record(passenger: Passenger) -> PassengerRecord:
    return PassengerRecord(
        id=passenger.id,
        given_name=passenger.given_name,
        family_name=passenger.family_name,
    )


def passenger_from_record(record: PassengerRecord) -> Passenger:
    return _validate_domain(
        Passenger,
        {
            "id": record.id,
            "given_name": record.given_name,
            "family_name": record.family_name,
        },
        entity_name="passenger",
        entity_id=record.id,
    )


def flight_to_record(flight: Flight) -> FlightRecord:
    return FlightRecord(
        id=flight.id,
        carrier_code=flight.carrier_code,
        flight_number=flight.flight_number,
        origin=flight.origin,
        destination=flight.destination,
        scheduled_departure=flight.scheduled_departure,
        scheduled_arrival=flight.scheduled_arrival,
    )


def flight_from_record(record: FlightRecord) -> Flight:
    return _validate_domain(
        Flight,
        {
            "id": record.id,
            "carrier_code": record.carrier_code,
            "flight_number": record.flight_number,
            "origin": record.origin,
            "destination": record.destination,
            "scheduled_departure": record.scheduled_departure,
            "scheduled_arrival": record.scheduled_arrival,
        },
        entity_name="flight",
        entity_id=record.id,
    )


def booking_to_record(booking: Booking) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        passenger_links=[
            BookingPassengerRecord(
                booking_id=booking.id,
                passenger_id=passenger_id,
            )
            for passenger_id in booking.passenger_ids
        ],
        segments=[
            ItinerarySegmentRecord(
                id=segment.id,
                booking_id=booking.id,
                flight_id=segment.flight_id,
                sequence=segment.sequence,
            )
            for segment in booking.segments
        ],
    )


def booking_from_record(record: BookingRecord) -> Booking:
    return _validate_domain(
        Booking,
        {
            "id": record.id,
            "passenger_ids": tuple(
                link.passenger_id for link in record.passenger_links
            ),
            "segments": tuple(
                {
                    "id": segment.id,
                    "flight_id": segment.flight_id,
                    "sequence": segment.sequence,
                }
                for segment in sorted(
                    record.segments,
                    key=lambda item: item.sequence,
                )
            ),
        },
        entity_name="booking",
        entity_id=record.id,
    )


def disruption_to_record(disruption: Disruption) -> DisruptionRecord:
    delay_minutes: int | None = None
    cancellation_reason: str | None = None
    arriving_flight_id: str | None = None
    missed_flight_id: str | None = None

    if isinstance(disruption.details, DelayedFlightDetails):
        delay_minutes = disruption.details.delay_minutes
    elif isinstance(disruption.details, CancelledFlightDetails):
        cancellation_reason = disruption.details.reason
    elif isinstance(disruption.details, MissedConnectionDetails):
        arriving_flight_id = disruption.details.arriving_flight_id
        missed_flight_id = disruption.details.missed_flight_id

    return DisruptionRecord(
        id=disruption.id,
        affected_flight_id=disruption.affected_flight_id,
        affected_segment_id=disruption.affected_segment_id,
        occurred_at=disruption.occurred_at,
        type=disruption.details.type.value,
        delay_minutes=delay_minutes,
        cancellation_reason=cancellation_reason,
        arriving_flight_id=arriving_flight_id,
        missed_flight_id=missed_flight_id,
    )


def disruption_from_record(record: DisruptionRecord) -> Disruption:
    details: dict[str, object] = {"type": record.type}

    if record.delay_minutes is not None:
        details["delay_minutes"] = record.delay_minutes
    if record.cancellation_reason is not None:
        details["reason"] = record.cancellation_reason
    if record.arriving_flight_id is not None:
        details["arriving_flight_id"] = record.arriving_flight_id
    if record.missed_flight_id is not None:
        details["missed_flight_id"] = record.missed_flight_id

    return _validate_domain(
        Disruption,
        {
            "id": record.id,
            "affected_flight_id": record.affected_flight_id,
            "affected_segment_id": record.affected_segment_id,
            "occurred_at": record.occurred_at,
            "details": details,
        },
        entity_name="disruption",
        entity_id=record.id,
    )


def policy_to_record(policy: DisruptionPolicy) -> DisruptionPolicyRecord:
    return DisruptionPolicyRecord(
        id=policy.id,
        name=policy.name,
        summary=policy.summary,
        rebooking_window_hours=policy.rebooking_window_hours,
        allows_next_day=policy.allows_next_day,
        type_links=[
            DisruptionPolicyTypeRecord(
                policy_id=policy.id,
                disruption_type=disruption_type.value,
                sequence=sequence,
            )
            for sequence, disruption_type in enumerate(
                policy.applicable_types,
                start=1,
            )
        ],
    )


def policy_from_record(record: DisruptionPolicyRecord) -> DisruptionPolicy:
    ordered_types = sorted(
        record.type_links,
        key=lambda link: link.sequence,
    )

    return _validate_domain(
        DisruptionPolicy,
        {
            "id": record.id,
            "name": record.name,
            "summary": record.summary,
            "applicable_types": tuple(link.disruption_type for link in ordered_types),
            "rebooking_window_hours": record.rebooking_window_hours,
            "allows_next_day": record.allows_next_day,
        },
        entity_name="policy",
        entity_id=record.id,
    )


def recovery_case_to_record(
    recovery_case: RecoveryCase,
) -> RecoveryCaseRecord:
    return RecoveryCaseRecord(
        id=recovery_case.id,
        title=recovery_case.title,
        booking_id=recovery_case.booking_id,
        disruption_id=recovery_case.disruption_id,
        policy_id=recovery_case.policy_id,
    )


def recovery_case_from_record(
    record: RecoveryCaseRecord,
) -> RecoveryCase:
    return _validate_domain(
        RecoveryCase,
        {
            "id": record.id,
            "title": record.title,
            "booking_id": record.booking_id,
            "disruption_id": record.disruption_id,
            "policy_id": record.policy_id,
        },
        entity_name="recovery case",
        entity_id=record.id,
    )
