"""Core airline domain models and invariants."""

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PassengerId = Annotated[str, StringConstraints(pattern=r"^PAX-[A-Z0-9]+$")]
FlightId = Annotated[str, StringConstraints(pattern=r"^FLT-[A-Z0-9]+$")]
AirportCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
CarrierCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
FlightNumber = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{2,3}$")]
BookingId = Annotated[str, StringConstraints(pattern=r"^BKG-[A-Z0-9]+$")]
SegmentId = Annotated[str, StringConstraints(pattern=r"^SEG-[A-Z0-9]+$")]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Passenger(DomainModel):
    id: PassengerId
    given_name: NonEmptyText
    family_name: NonEmptyText


class Flight(DomainModel):
    id: FlightId
    carrier_code: CarrierCode
    flight_number: FlightNumber
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime

    @field_validator("scheduled_departure", "scheduled_arrival")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_route_and_schedule(self) -> Self:
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")

        if self.scheduled_arrival <= self.scheduled_departure:
            raise ValueError("scheduled_arrival must be after scheduled_departure")

        return self


class ItinerarySegment(DomainModel):
    id: SegmentId
    flight_id: FlightId
    sequence: PositiveInt


class Booking(DomainModel):
    id: BookingId
    passenger_ids: tuple[PassengerId, ...]
    segments: tuple[ItinerarySegment, ...]

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if not self.passenger_ids:
            raise ValueError("booking must contain at least one passenger")

        if len(set(self.passenger_ids)) != len(self.passenger_ids):
            raise ValueError("booking passenger identifiers must be unique")

        if not self.segments:
            raise ValueError("booking must contain at least one segment")

        segment_ids = [segment.id for segment in self.segments]
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError("booking segment identifiers must be unique")

        flight_ids = [segment.flight_id for segment in self.segments]
        if len(set(flight_ids)) != len(flight_ids):
            raise ValueError("booking flight identifiers must be unique")

        expected_sequences = list(range(1, len(self.segments) + 1))
        actual_sequences = [segment.sequence for segment in self.segments]
        if actual_sequences != expected_sequences:
            raise ValueError(
                "segment sequence must be ordered and contiguous starting at 1"
            )

        return self


DisruptionId = Annotated[
    str,
    StringConstraints(pattern=r"^DIS-[A-Z0-9]+$"),
]
PolicyId = Annotated[
    str,
    StringConstraints(pattern=r"^POL-[A-Z0-9]+$"),
]
RecoveryCaseId = Annotated[
    str,
    StringConstraints(pattern=r"^CASE-[A-Z0-9]+$"),
]


def validate_itinerary(
    booking: Booking,
    flights_by_id: Mapping[str, Flight],
) -> None:
    ordered_flights: list[Flight] = []

    for segment in booking.segments:
        flight = flights_by_id.get(segment.flight_id)
        if flight is None:
            raise ValueError(
                f"booking {booking.id} segment {segment.id} "
                f"references missing flight {segment.flight_id}"
            )
        ordered_flights.append(flight)

    for previous, current in pairwise(ordered_flights):
        if previous.destination != current.origin:
            raise ValueError(
                f"itinerary is geographically disconnected: "
                f"{previous.id} arrives at {previous.destination}, "
                f"but {current.id} departs from {current.origin}"
            )

        if current.scheduled_departure < previous.scheduled_arrival:
            raise ValueError(
                f"itinerary has a negative connection time: "
                f"{current.id} departs before {previous.id} arrives"
            )


class DisruptionType(StrEnum):
    DELAYED_FLIGHT = "delayed_flight"
    CANCELLED_FLIGHT = "cancelled_flight"
    MISSED_CONNECTION = "missed_connection"


class DelayedFlightDetails(DomainModel):
    type: Literal[DisruptionType.DELAYED_FLIGHT] = DisruptionType.DELAYED_FLIGHT
    delay_minutes: PositiveInt


class CancelledFlightDetails(DomainModel):
    type: Literal[DisruptionType.CANCELLED_FLIGHT] = DisruptionType.CANCELLED_FLIGHT
    reason: NonEmptyText


class MissedConnectionDetails(DomainModel):
    type: Literal[DisruptionType.MISSED_CONNECTION] = DisruptionType.MISSED_CONNECTION
    arriving_flight_id: FlightId
    missed_flight_id: FlightId

    @model_validator(mode="after")
    def require_different_flights(self) -> Self:
        if self.arriving_flight_id == self.missed_flight_id:
            raise ValueError("arriving and missed flight identifiers must differ")
        return self


DisruptionDetails = Annotated[
    DelayedFlightDetails | CancelledFlightDetails | MissedConnectionDetails,
    Field(discriminator="type"),
]


class Disruption(DomainModel):
    id: DisruptionId
    affected_flight_id: FlightId
    affected_segment_id: SegmentId
    occurred_at: datetime
    details: DisruptionDetails

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_affected_flight(self) -> Self:
        if (
            isinstance(self.details, MissedConnectionDetails)
            and self.affected_flight_id != self.details.missed_flight_id
        ):
            raise ValueError("a missed connection must affect the missed flight")
        return self


class DisruptionPolicy(DomainModel):
    id: PolicyId
    name: NonEmptyText
    summary: NonEmptyText
    applicable_types: tuple[DisruptionType, ...]
    rebooking_window_hours: PositiveInt
    allows_next_day: bool

    @model_validator(mode="after")
    def validate_applicable_types(self) -> Self:
        if not self.applicable_types:
            raise ValueError("policy must apply to at least one disruption type")

        if len(set(self.applicable_types)) != len(self.applicable_types):
            raise ValueError("policy disruption types must be unique")

        return self


class RecoveryCase(DomainModel):
    id: RecoveryCaseId
    title: NonEmptyText
    booking_id: BookingId
    disruption_id: DisruptionId
    policy_id: PolicyId
