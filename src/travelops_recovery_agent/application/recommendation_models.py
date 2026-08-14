"""Typed contracts for evidence-grounded recovery recommendations."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecommendationContract(BaseModel):
    """Strict immutable base used by application, checkpoints, and HTTP views."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RecommendationOutcome(StrEnum):
    RECOMMENDED = "recommended"
    NO_SAFE_OPTION = "no_safe_option"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class EvidenceKind(StrEnum):
    STORED_FLIGHT = "stored_flight"
    FLIGHT_STATUS = "flight_status"
    SCHEDULE = "schedule"
    MINIMUM_CONNECTION_TIME = "minimum_connection_time"
    SEAT_AVAILABILITY = "seat_availability"
    TICKET_RULE = "ticket_rule"
    DISRUPTION_POLICY = "disruption_policy"


class RecommendationRule(StrEnum):
    FLIGHTS_EXIST = "flights_exist"
    ROUTE_CONTINUITY = "route_continuity"
    FLIGHT_AND_CONNECTION_TIMES = "flight_and_connection_times"
    MINIMUM_CONNECTION_TIME = "minimum_connection_time"
    GROUP_SEAT_AVAILABILITY = "group_seat_availability"
    TICKET_AND_REBOOKING_RULES = "ticket_and_rebooking_rules"
    STORED_FLIGHT_STATUS = "stored_flight_status"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    MISSING_EVIDENCE = "missing_evidence"
    NOT_EVALUATED = "not_evaluated"


class EvidenceReference(RecommendationContract):
    evidence_id: str
    kind: EvidenceKind
    source: str
    summary: str
    observed_at: datetime | None = None

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("evidence timestamps must be timezone-aware")
        return value


class RecommendationSegment(RecommendationContract):
    flight_id: str
    service: str
    origin: str
    destination: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    operational_departure: datetime
    operational_arrival: datetime
    status: str
    available_seats: Annotated[int | None, Field(ge=0)] = None


class ValidationCheck(RecommendationContract):
    rule: RecommendationRule
    status: ValidationStatus
    summary: str
    evidence_ids: tuple[str, ...] = ()


class OptionValidation(RecommendationContract):
    valid: bool
    evidence_complete: bool
    checks: tuple[ValidationCheck, ...]
    rejection_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_derived_outcome(self) -> Self:
        derived_valid = bool(self.checks) and all(
            check.status is ValidationStatus.PASSED for check in self.checks
        )
        derived_complete = all(
            check.status is not ValidationStatus.MISSING_EVIDENCE
            for check in self.checks
        )
        if self.valid != derived_valid:
            raise ValueError("option validity must be derived from all checks")
        if self.evidence_complete != derived_complete:
            raise ValueError("evidence completeness must be derived from checks")
        if self.valid and self.rejection_reasons:
            raise ValueError("valid options cannot have rejection reasons")
        if not self.valid and not self.rejection_reasons:
            raise ValueError("invalid options require rejection reasons")
        return self


class RankingInputs(RecommendationContract):
    arrival_time: datetime
    connection_count: Annotated[int, Field(ge=0)]
    total_wait_minutes: Annotated[int, Field(ge=0)]
    minimum_available_seats: Annotated[int, Field(ge=0)]
    passenger_count: Annotated[int, Field(gt=0)]
    seat_surplus: Annotated[int, Field(ge=0)]
    policy_compatible: bool
    ticket_compatible: bool
    rank_position: Annotated[int, Field(gt=0)] | None = None

    @field_validator("arrival_time")
    @classmethod
    def require_arrival_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ranking arrival time must be timezone-aware")
        return value


class RecommendationOption(RecommendationContract):
    option_id: str
    segments: tuple[RecommendationSegment, ...]
    validation: OptionValidation
    evidence_references: tuple[EvidenceReference, ...]
    ranking_inputs: RankingInputs | None = None
    tradeoffs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_and_ranking(self) -> Self:
        evidence_ids = [item.evidence_id for item in self.evidence_references]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("option evidence references must be unique")
        cited_ids = {
            evidence_id
            for check in self.validation.checks
            for evidence_id in check.evidence_ids
        }
        if not cited_ids.issubset(evidence_ids):
            raise ValueError("validation checks must cite option evidence")
        if self.validation.valid:
            if not self.segments or self.ranking_inputs is None:
                raise ValueError("valid options require segments and ranking inputs")
        elif self.ranking_inputs is not None:
            raise ValueError("invalid options cannot enter ranking")
        return self


class RecommendationResult(RecommendationContract):
    case_id: str
    outcome: RecommendationOutcome
    recommended_itinerary: RecommendationOption | None = None
    other_validated_options: tuple[RecommendationOption, ...] = ()
    option_results: tuple[RecommendationOption, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    evidence_completeness: EvidenceCompleteness
    escalation_reason: str | None = None
    ranking_method: str

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome is RecommendationOutcome.RECOMMENDED:
            if self.recommended_itinerary is None or self.escalation_reason is not None:
                raise ValueError(
                    "recommended outcomes require one option and no escalation"
                )
            if not self.recommended_itinerary.validation.valid:
                raise ValueError("the recommended itinerary must be validated")
        elif self.recommended_itinerary is not None:
            raise ValueError("escalation outcomes cannot contain a recommendation")
        elif not self.escalation_reason:
            raise ValueError("escalation outcomes require a clear reason")

        valid_ids = {
            option.option_id
            for option in self.option_results
            if option.validation.valid
        }
        exposed_ids = {option.option_id for option in self.other_validated_options}
        if self.recommended_itinerary is not None:
            exposed_ids.add(self.recommended_itinerary.option_id)
        if exposed_ids != valid_ids:
            raise ValueError(
                "recommended and other options must expose every valid option"
            )
        return self
