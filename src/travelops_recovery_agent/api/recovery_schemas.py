"""Frontend-oriented HTTP view models for recovery operations."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from travelops_recovery_agent.application.query_models import OperationalFlightStatus
from travelops_recovery_agent.application.recommendation_models import (
    RecommendationResult,
)
from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRule,
    RuleStatus,
)
from travelops_recovery_agent.domain.models import (
    AirportCode,
    BookingId,
    DisruptionId,
    DisruptionType,
    FlightId,
    NonEmptyText,
    PassengerId,
    PolicyId,
    RecoveryCaseId,
    SegmentId,
)


class ApiViewModel(BaseModel):
    """Strict immutable base for versioned browser API models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RecoveryCaseRouteView(ApiViewModel):
    origin: AirportCode
    destination: AirportCode


class RecoveryCaseQueueItemView(ApiViewModel):
    case_id: RecoveryCaseId
    title: NonEmptyText
    booking_id: BookingId
    route: RecoveryCaseRouteView
    passenger_count: PositiveInt
    disruption_type: DisruptionType
    affected_flight_id: FlightId
    occurred_at: datetime
    operational_status: OperationalFlightStatus
    delay_minutes: PositiveInt | None
    cancellation_reason: NonEmptyText | None
    journey_departure: datetime
    journey_arrival: datetime


class RecoveryCaseQueueView(ApiViewModel):
    cases: tuple[RecoveryCaseQueueItemView, ...]


class PassengerView(ApiViewModel):
    passenger_id: PassengerId
    display_name: NonEmptyText


class ItinerarySegmentView(ApiViewModel):
    segment_id: SegmentId
    sequence: PositiveInt
    flight_id: FlightId
    service: NonEmptyText
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime
    operational_status: OperationalFlightStatus
    delay_minutes: PositiveInt | None
    cancellation_reason: NonEmptyText | None
    affected: bool


class DisruptionEvidenceView(ApiViewModel):
    disruption_id: DisruptionId
    disruption_type: DisruptionType
    affected_flight_id: FlightId
    affected_segment_id: SegmentId
    occurred_at: datetime
    delay_minutes: PositiveInt | None = None
    cancellation_reason: NonEmptyText | None = None
    arriving_flight_id: FlightId | None = None
    missed_flight_id: FlightId | None = None


class PolicyEvidenceView(ApiViewModel):
    policy_id: PolicyId
    name: NonEmptyText
    summary: NonEmptyText
    applicable_types: tuple[DisruptionType, ...]
    rebooking_window_hours: PositiveInt
    allows_next_day: bool


class AlternativeSearchDefaultsView(ApiViewModel):
    origin: AirportCode
    destination: AirportCode
    earliest_departure: datetime
    latest_arrival: datetime
    passenger_count: PositiveInt
    max_connections: Literal[0, 1] = 1


class RecoveryCaseWorkspaceView(ApiViewModel):
    case_id: RecoveryCaseId
    title: NonEmptyText
    booking_id: BookingId
    passengers: tuple[PassengerView, ...]
    itinerary: tuple[ItinerarySegmentView, ...]
    disruption: DisruptionEvidenceView
    policy: PolicyEvidenceView
    search_defaults: AlternativeSearchDefaultsView
    recommendation: RecommendationResult


class AlternativeSearchRequest(ApiViewModel):
    case_id: RecoveryCaseId
    earliest_departure: datetime
    latest_arrival: datetime
    max_connections: Literal[0, 1] = 1

    @field_validator("earliest_departure", "latest_arrival")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("search timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "AlternativeSearchRequest":
        if self.latest_arrival <= self.earliest_departure:
            raise ValueError("latest_arrival must be after earliest_departure")
        return self


class CandidateSegmentView(ApiViewModel):
    flight_id: FlightId
    service: NonEmptyText
    origin: AirportCode
    destination: AirportCode
    scheduled_departure: datetime
    scheduled_arrival: datetime


class AlternativeCandidateView(ApiViewModel):
    candidate_id: NonEmptyText
    segments: tuple[CandidateSegmentView, ...]
    connection_minutes: tuple[Annotated[int, Field(ge=0)], ...]
    scheduled_duration_minutes: PositiveInt
    validation_status: Literal["not_validated"] = "not_validated"


class AlternativeSearchView(ApiViewModel):
    case_id: RecoveryCaseId
    route: RecoveryCaseRouteView
    passenger_count: PositiveInt
    candidates: tuple[AlternativeCandidateView, ...]
    inventory_status: Literal["not_evaluated"] = "not_evaluated"
    deferred_validations: tuple[Literal["seat_inventory", "ticket_rules"], ...] = (
        "seat_inventory",
        "ticket_rules",
    )


class ItineraryValidationRequest(ApiViewModel):
    case_id: RecoveryCaseId
    candidate_id: NonEmptyText
    flight_ids: Annotated[tuple[FlightId, ...], Field(min_length=1, max_length=2)]

    @model_validator(mode="after")
    def require_unique_flights(self) -> "ItineraryValidationRequest":
        if len(set(self.flight_ids)) != len(self.flight_ids):
            raise ValueError("candidate flight identifiers must be unique")
        return self


class ValidationRuleView(ApiViewModel):
    rule: (
        ItineraryRule
        | Literal["minimum_connection_policy", "seat_inventory", "ticket_rules"]
    )
    status: RuleStatus | Literal["deferred"]
    reason: NonEmptyText


class ItineraryValidationView(ApiViewModel):
    case_id: RecoveryCaseId
    candidate_id: NonEmptyText
    flight_ids: tuple[FlightId, ...]
    structurally_valid: bool
    rules: tuple[ValidationRuleView, ...]


class ApiErrorDetail(ApiViewModel):
    code: Literal["not_found", "service_unavailable"]
    message: NonEmptyText
    retryable: bool


class ApiErrorView(ApiViewModel):
    error: ApiErrorDetail
