"""Typed inputs and outputs for operational tools."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRule,
    RuleStatus,
)
from travelops_recovery_agent.domain.models import (
    AirportCode,
    BookingId,
    CarrierCode,
    DisruptionId,
    DisruptionType,
    FlightId,
    FlightNumber,
    PassengerId,
    PolicyId,
    RecoveryCaseId,
    SegmentId,
)
from travelops_recovery_agent.tools.contracts import NonEmptyText


class ToolModel(BaseModel):
    """Strict immutable base for tool inputs and outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetBookingInput(ToolModel):
    """Stable booking identifier accepted by get_booking."""

    booking_id: BookingId


class BookingPassenger(ToolModel):
    """Minimized passenger identity returned with a booking."""

    passenger_id: PassengerId
    display_name: NonEmptyText


class BookingItinerarySegment(ToolModel):
    """Scheduled flight facts for one ordered booking segment."""

    segment_id: SegmentId
    sequence: int
    flight_id: FlightId
    carrier_code: CarrierCode
    flight_number: FlightNumber
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime


class GetBookingOutput(ToolModel):
    """Minimized passenger view and ordered itinerary for one booking."""

    booking_id: BookingId
    passengers: tuple[BookingPassenger, ...]
    itinerary: tuple[BookingItinerarySegment, ...]


class FlightOperationalStatus(StrEnum):
    """Synthetic operational states exposed by the tool."""

    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class GetFlightStatusInput(ToolModel):
    """Stable flight identifier accepted by get_flight_status."""

    flight_id: FlightId


class FlightStatusDisruption(ToolModel):
    """Safe disruption evidence related to a flight."""

    disruption_id: DisruptionId
    disruption_type: DisruptionType
    occurred_at: datetime


class GetFlightStatusOutput(ToolModel):
    """Scheduled facts and deterministic synthetic operational status."""

    flight_id: FlightId
    carrier_code: CarrierCode
    flight_number: FlightNumber
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime
    operational_status: FlightOperationalStatus
    delay_minutes: int | None
    cancellation_reason: str | None
    related_disruptions: tuple[FlightStatusDisruption, ...]
    source: Literal["synthetic_dataset"] = "synthetic_dataset"


class RecoveryCasePolicyReference(ToolModel):
    """Recovery-case reference used to resolve a disruption policy."""

    type: Literal["recovery_case"]
    id: RecoveryCaseId


class DisruptionPolicyReference(ToolModel):
    """Disruption reference used to resolve a disruption policy."""

    type: Literal["disruption"]
    id: DisruptionId


PolicyReference = Annotated[
    RecoveryCasePolicyReference | DisruptionPolicyReference,
    Field(discriminator="type"),
]


class GetDisruptionPolicyInput(ToolModel):
    """One explicit typed reference accepted by get_disruption_policy."""

    reference: PolicyReference


class GetDisruptionPolicyOutput(ToolModel):
    """Structured policy facts relevant to one stored disruption."""

    resolved_via: Literal["recovery_case", "disruption"]
    recovery_case_id: RecoveryCaseId
    disruption_id: DisruptionId
    disruption_type: DisruptionType
    affected_flight_id: FlightId
    policy_id: PolicyId
    name: NonEmptyText
    summary: NonEmptyText
    applicable_types: tuple[DisruptionType, ...]
    rebooking_window_hours: PositiveInt
    allows_next_day: bool


class SearchAlternativeItinerariesInput(ToolModel):
    """Explicit route, time window, and passenger requirements for candidate search."""

    origin: AirportCode
    destination: AirportCode
    earliest_departure: datetime
    latest_arrival: datetime
    passenger_count: PositiveInt
    max_connections: Literal[0, 1] = 1

    @field_validator("earliest_departure", "latest_arrival")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("search timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_route_and_window(self) -> Self:
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.latest_arrival <= self.earliest_departure:
            raise ValueError("latest_arrival must be after earliest_departure")
        return self


class AlternativeFlightSegment(ToolModel):
    """Scheduled facts for one flight in an alternative candidate."""

    flight_id: FlightId
    carrier_code: CarrierCode
    flight_number: FlightNumber
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime


class AlternativeItineraryCandidate(ToolModel):
    """Deterministic candidate that has not yet passed final validation."""

    candidate_id: NonEmptyText
    flights: tuple[AlternativeFlightSegment, ...]
    connection_minutes: tuple[Annotated[int, Field(ge=0)], ...]
    scheduled_duration_minutes: PositiveInt
    validation_status: Literal["not_validated"] = "not_validated"


class SearchAlternativeItinerariesOutput(ToolModel):
    """Deterministic candidates with explicit deferred availability checks."""

    origin: AirportCode
    destination: AirportCode
    earliest_departure: datetime
    latest_arrival: datetime
    passenger_count: PositiveInt
    candidates: tuple[AlternativeItineraryCandidate, ...]
    inventory_status: Literal["not_evaluated"] = "not_evaluated"
    deferred_validations: tuple[Literal["seat_inventory", "ticket_rules"], ...] = (
        "seat_inventory",
        "ticket_rules",
    )


class CandidateItineraryInput(ToolModel):
    """Candidate identity and ordered stored flight identifiers to validate."""

    candidate_id: NonEmptyText
    flight_ids: Annotated[tuple[FlightId, ...], Field(min_length=1, max_length=2)]
    passenger_count: PositiveInt

    @model_validator(mode="after")
    def require_unique_flights(self) -> Self:
        if len(set(self.flight_ids)) != len(self.flight_ids):
            raise ValueError("candidate flight identifiers must be unique")
        return self


class ValidateItineraryInput(ToolModel):
    """Typed candidate accepted by deterministic itinerary validation."""

    candidate: CandidateItineraryInput


class ItineraryValidationRuleOutput(ToolModel):
    """Structured status and reason for one fixed validation rule."""

    rule: ItineraryRule
    status: RuleStatus
    reason: NonEmptyText


class ValidateItineraryOutput(ToolModel):
    """Deterministic validity with explicit Phase 9 deferrals."""

    candidate_id: NonEmptyText
    flight_ids: tuple[FlightId, ...]
    passenger_count: PositiveInt
    valid: bool
    rules: tuple[ItineraryValidationRuleOutput, ...]
    deferred_validations: tuple[
        Literal["minimum_connection_policy", "seat_inventory", "ticket_rules"],
        ...,
    ] = (
        "minimum_connection_policy",
        "seat_inventory",
        "ticket_rules",
    )
