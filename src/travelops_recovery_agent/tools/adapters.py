"""Adapters exposing application services as guarded operational tools."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import ValidationError

from travelops_recovery_agent.application.query_models import (
    AlternativeItinerary,
    AlternativeSearchRequirements,
    CompleteBooking,
    FlightStatus,
    ItineraryValidationResult,
    ResolvedDisruptionPolicy,
)
from travelops_recovery_agent.application.query_services import (
    OperationalQueryService,
)
from travelops_recovery_agent.tools.contracts import (
    ToolAuditMetadata,
    ToolAuditOutcome,
    ToolError,
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolResult,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import (
    AlternativeFlightSegment,
    AlternativeItineraryCandidate,
    BookingItinerarySegment,
    BookingPassenger,
    FlightOperationalStatus,
    FlightStatusDisruption,
    GetBookingInput,
    GetBookingOutput,
    GetDisruptionPolicyInput,
    GetDisruptionPolicyOutput,
    GetFlightStatusInput,
    GetFlightStatusOutput,
    ItineraryValidationRuleOutput,
    RecoveryCasePolicyReference,
    SearchAlternativeItinerariesInput,
    SearchAlternativeItinerariesOutput,
    ValidateItineraryInput,
    ValidateItineraryOutput,
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


class _ReadOnlyToolAdapter:
    """Share safe audit and failure construction across read-only tools."""

    name: str
    required_permission: ToolPermission

    def __init__(
        self,
        query_service: OperationalQueryService,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._query_service = query_service
        self._clock = clock

    def _failure(
        self,
        context: ToolExecutionContext,
        started_at: datetime,
        code: ToolErrorCode,
        message: str,
        *,
        retryable: bool,
        outcome: ToolAuditOutcome,
        completed_at: datetime | None = None,
    ) -> ToolFailure:
        resolved_completed_at = completed_at or self._clock()
        return ToolFailure(
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
            ),
            audit=self._audit(
                context,
                started_at,
                resolved_completed_at,
                outcome,
            ),
        )

    def _audit(
        self,
        context: ToolExecutionContext,
        started_at: datetime,
        completed_at: datetime,
        outcome: ToolAuditOutcome,
    ) -> ToolAuditMetadata:
        duration_ms = max(
            0,
            round((completed_at - started_at).total_seconds() * 1000),
        )
        return ToolAuditMetadata(
            tool_name=self.name,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            required_permission=self.required_permission,
            outcome=outcome,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )


class GetBookingTool(_ReadOnlyToolAdapter):
    """Safely expose the read-only booking application query."""

    name = "get_booking"
    required_permission = ToolPermission.READ_BOOKING

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolResult[GetBookingOutput]:
        """Validate and execute one authorized booking lookup."""

        started_at = self._clock()

        try:
            tool_input = GetBookingInput.model_validate(input_data)
        except ValidationError:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.INVALID_INPUT,
                "input did not match the get_booking schema",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if self.required_permission not in context.permissions:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.PERMISSION_DENIED,
                "permission denied",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if started_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        try:
            complete_booking = self._query_service.get_booking(tool_input.booking_id)
            output = (
                None
                if complete_booking is None
                else self._build_output(complete_booking)
            )
        except Exception:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEPENDENCY_FAILURE,
                "operational dependency failed",
                retryable=True,
                outcome=ToolAuditOutcome.FAILED,
            )

        completed_at = self._clock()

        if completed_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.FAILED,
                completed_at=completed_at,
            )

        if output is None:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.NOT_FOUND,
                f"booking {tool_input.booking_id} was not found",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
                completed_at=completed_at,
            )

        return ToolSuccess[GetBookingOutput](
            result=output,
            audit=self._audit(
                context,
                started_at,
                completed_at,
                ToolAuditOutcome.SUCCEEDED,
            ),
        )

    @staticmethod
    def _build_output(
        complete_booking: CompleteBooking,
    ) -> GetBookingOutput:
        passengers_by_id = {
            passenger.id: passenger for passenger in complete_booking.passengers
        }
        flights_by_id = {flight.id: flight for flight in complete_booking.flights}

        return GetBookingOutput(
            booking_id=complete_booking.booking.id,
            passengers=tuple(
                BookingPassenger(
                    passenger_id=passenger_id,
                    display_name=(
                        f"{passengers_by_id[passenger_id].given_name} "
                        f"{passengers_by_id[passenger_id].family_name}"
                    ),
                )
                for passenger_id in complete_booking.booking.passenger_ids
            ),
            itinerary=tuple(
                BookingItinerarySegment(
                    segment_id=segment.id,
                    sequence=segment.sequence,
                    flight_id=flight.id,
                    carrier_code=flight.carrier_code,
                    flight_number=flight.flight_number,
                    origin=flight.origin,
                    destination=flight.destination,
                    scheduled_departure=flight.scheduled_departure,
                    scheduled_arrival=flight.scheduled_arrival,
                )
                for segment in complete_booking.booking.segments
                for flight in (flights_by_id[segment.flight_id],)
            ),
        )


class GetFlightStatusTool(_ReadOnlyToolAdapter):
    """Safely expose deterministic synthetic flight status."""

    name = "get_flight_status"
    required_permission = ToolPermission.READ_FLIGHT_STATUS

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolResult[GetFlightStatusOutput]:
        """Validate and execute one authorized flight-status lookup."""

        started_at = self._clock()

        try:
            tool_input = GetFlightStatusInput.model_validate(input_data)
        except ValidationError:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.INVALID_INPUT,
                "input did not match the get_flight_status schema",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if self.required_permission not in context.permissions:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.PERMISSION_DENIED,
                "permission denied",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if started_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        try:
            flight_status = self._query_service.get_flight_status(tool_input.flight_id)
            output = (
                None if flight_status is None else self._build_output(flight_status)
            )
        except Exception:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEPENDENCY_FAILURE,
                "operational dependency failed",
                retryable=True,
                outcome=ToolAuditOutcome.FAILED,
            )

        completed_at = self._clock()
        if completed_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.FAILED,
                completed_at=completed_at,
            )

        if output is None:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.NOT_FOUND,
                f"flight {tool_input.flight_id} was not found",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
                completed_at=completed_at,
            )

        return ToolSuccess[GetFlightStatusOutput](
            result=output,
            audit=self._audit(
                context,
                started_at,
                completed_at,
                ToolAuditOutcome.SUCCEEDED,
            ),
        )

    @staticmethod
    def _build_output(flight_status: FlightStatus) -> GetFlightStatusOutput:
        flight = flight_status.flight
        return GetFlightStatusOutput(
            flight_id=flight.id,
            carrier_code=flight.carrier_code,
            flight_number=flight.flight_number,
            origin=flight.origin,
            destination=flight.destination,
            scheduled_departure=flight.scheduled_departure,
            scheduled_arrival=flight.scheduled_arrival,
            operational_status=FlightOperationalStatus(flight_status.status.value),
            delay_minutes=flight_status.delay_minutes,
            cancellation_reason=flight_status.cancellation_reason,
            related_disruptions=tuple(
                FlightStatusDisruption(
                    disruption_id=disruption.id,
                    disruption_type=disruption.details.type,
                    occurred_at=disruption.occurred_at,
                )
                for disruption in flight_status.related_disruptions
            ),
        )


class GetDisruptionPolicyTool(_ReadOnlyToolAdapter):
    """Safely expose structured disruption-policy resolution."""

    name = "get_disruption_policy"
    required_permission = ToolPermission.READ_DISRUPTION_POLICY

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolResult[GetDisruptionPolicyOutput]:
        """Validate and execute one authorized policy lookup."""

        started_at = self._clock()
        try:
            tool_input = GetDisruptionPolicyInput.model_validate(input_data)
        except ValidationError:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.INVALID_INPUT,
                "input did not match the get_disruption_policy schema",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if self.required_permission not in context.permissions:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.PERMISSION_DENIED,
                "permission denied",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if started_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        reference = tool_input.reference
        try:
            if isinstance(reference, RecoveryCasePolicyReference):
                resolution = self._query_service.get_disruption_policy_for_case(
                    reference.id
                )
                resolved_via: Literal["recovery_case", "disruption"] = "recovery_case"
            else:
                resolution = self._query_service.get_disruption_policy_for_disruption(
                    reference.id
                )
                resolved_via = "disruption"
        except Exception:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEPENDENCY_FAILURE,
                "operational dependency failed",
                retryable=True,
                outcome=ToolAuditOutcome.FAILED,
            )

        completed_at = self._clock()
        if completed_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.FAILED,
                completed_at=completed_at,
            )

        if resolution is None:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.NOT_FOUND,
                f"policy reference {reference.id} was not found",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
                completed_at=completed_at,
            )

        return ToolSuccess[GetDisruptionPolicyOutput](
            result=self._build_output(resolution, resolved_via),
            audit=self._audit(
                context,
                started_at,
                completed_at,
                ToolAuditOutcome.SUCCEEDED,
            ),
        )

    @staticmethod
    def _build_output(
        resolution: ResolvedDisruptionPolicy,
        resolved_via: Literal["recovery_case", "disruption"],
    ) -> GetDisruptionPolicyOutput:
        disruption = resolution.disruption
        policy = resolution.policy
        return GetDisruptionPolicyOutput(
            resolved_via=resolved_via,
            recovery_case_id=resolution.recovery_case.id,
            disruption_id=disruption.id,
            disruption_type=disruption.details.type,
            affected_flight_id=disruption.affected_flight_id,
            policy_id=policy.id,
            name=policy.name,
            summary=policy.summary,
            applicable_types=policy.applicable_types,
            rebooking_window_hours=policy.rebooking_window_hours,
            allows_next_day=policy.allows_next_day,
        )


class SearchAlternativeItinerariesTool(_ReadOnlyToolAdapter):
    """Safely expose deterministic synthetic itinerary candidate search."""

    name = "search_alternative_itineraries"
    required_permission = ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolResult[SearchAlternativeItinerariesOutput]:
        """Validate and execute one authorized candidate search."""

        started_at = self._clock()
        try:
            tool_input = SearchAlternativeItinerariesInput.model_validate(input_data)
        except ValidationError:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.INVALID_INPUT,
                "input did not match the search_alternative_itineraries schema",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if self.required_permission not in context.permissions:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.PERMISSION_DENIED,
                "permission denied",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )
        if started_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        try:
            candidates = self._query_service.search_alternative_itineraries(
                AlternativeSearchRequirements(
                    origin=tool_input.origin,
                    destination=tool_input.destination,
                    earliest_departure=tool_input.earliest_departure,
                    latest_arrival=tool_input.latest_arrival,
                    max_connections=tool_input.max_connections,
                )
            )
            output = self._build_output(tool_input, candidates)
        except Exception:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEPENDENCY_FAILURE,
                "operational dependency failed",
                retryable=True,
                outcome=ToolAuditOutcome.FAILED,
            )

        completed_at = self._clock()
        if completed_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.FAILED,
                completed_at=completed_at,
            )

        return ToolSuccess[SearchAlternativeItinerariesOutput](
            result=output,
            audit=self._audit(
                context,
                started_at,
                completed_at,
                ToolAuditOutcome.SUCCEEDED,
            ),
        )

    @staticmethod
    def _build_output(
        tool_input: SearchAlternativeItinerariesInput,
        candidates: tuple[AlternativeItinerary, ...],
    ) -> SearchAlternativeItinerariesOutput:
        return SearchAlternativeItinerariesOutput(
            origin=tool_input.origin,
            destination=tool_input.destination,
            earliest_departure=tool_input.earliest_departure,
            latest_arrival=tool_input.latest_arrival,
            passenger_count=tool_input.passenger_count,
            candidates=tuple(
                AlternativeItineraryCandidate(
                    candidate_id=(
                        "CAND-" + "-".join(flight.id for flight in candidate.flights)
                    ),
                    flights=tuple(
                        AlternativeFlightSegment(
                            flight_id=flight.id,
                            carrier_code=flight.carrier_code,
                            flight_number=flight.flight_number,
                            origin=flight.origin,
                            destination=flight.destination,
                            scheduled_departure=flight.scheduled_departure,
                            scheduled_arrival=flight.scheduled_arrival,
                        )
                        for flight in candidate.flights
                    ),
                    connection_minutes=candidate.connection_minutes,
                    scheduled_duration_minutes=int(
                        (
                            candidate.flights[-1].scheduled_arrival
                            - candidate.flights[0].scheduled_departure
                        ).total_seconds()
                        // 60
                    ),
                )
                for candidate in candidates
            ),
        )


class ValidateItineraryTool(_ReadOnlyToolAdapter):
    """Safely expose deterministic validation of trusted stored flights."""

    name = "validate_itinerary"
    required_permission = ToolPermission.VALIDATE_ITINERARY

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolResult[ValidateItineraryOutput]:
        """Validate one authorized candidate without trusting caller claims."""

        started_at = self._clock()
        try:
            tool_input = ValidateItineraryInput.model_validate(input_data)
        except ValidationError:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.INVALID_INPUT,
                "input did not match the validate_itinerary schema",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        if self.required_permission not in context.permissions:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.PERMISSION_DENIED,
                "permission denied",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )
        if started_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
            )

        try:
            validation = self._query_service.validate_itinerary(
                tool_input.candidate.flight_ids
            )
        except Exception:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEPENDENCY_FAILURE,
                "operational dependency failed",
                retryable=True,
                outcome=ToolAuditOutcome.FAILED,
            )

        completed_at = self._clock()
        if completed_at >= context.deadline_at:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.DEADLINE_EXCEEDED,
                "deadline exceeded",
                retryable=False,
                outcome=ToolAuditOutcome.FAILED,
                completed_at=completed_at,
            )

        missing_rule = next(
            (
                rule
                for rule in validation.rules
                if rule.rule.value == "flights_exist" and rule.status.value == "failed"
            ),
            None,
        )
        if missing_rule is not None:
            return self._failure(
                context,
                started_at,
                ToolErrorCode.NOT_FOUND,
                missing_rule.reason,
                retryable=False,
                outcome=ToolAuditOutcome.REJECTED,
                completed_at=completed_at,
            )

        return ToolSuccess[ValidateItineraryOutput](
            result=self._build_output(tool_input, validation),
            audit=self._audit(
                context,
                started_at,
                completed_at,
                ToolAuditOutcome.SUCCEEDED,
            ),
        )

    @staticmethod
    def _build_output(
        tool_input: ValidateItineraryInput,
        validation: ItineraryValidationResult,
    ) -> ValidateItineraryOutput:
        return ValidateItineraryOutput(
            candidate_id=tool_input.candidate.candidate_id,
            flight_ids=validation.flight_ids,
            passenger_count=tool_input.candidate.passenger_count,
            valid=validation.valid,
            rules=tuple(
                ItineraryValidationRuleOutput(
                    rule=rule.rule,
                    status=rule.status,
                    reason=rule.reason,
                )
                for rule in validation.rules
            ),
        )
