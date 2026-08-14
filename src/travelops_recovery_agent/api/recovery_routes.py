"""Read-only HTTP routes for the Phase 5 operator dashboard."""

import logging
from datetime import timedelta
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from travelops_recovery_agent.api.recovery_schemas import (
    AlternativeCandidateView,
    AlternativeSearchDefaultsView,
    AlternativeSearchRequest,
    AlternativeSearchView,
    ApiErrorDetail,
    ApiErrorView,
    CandidateSegmentView,
    DisruptionEvidenceView,
    ItinerarySegmentView,
    ItineraryValidationRequest,
    ItineraryValidationView,
    PassengerView,
    PolicyEvidenceView,
    RecoveryCaseQueueItemView,
    RecoveryCaseQueueView,
    RecoveryCaseRouteView,
    RecoveryCaseWorkspaceView,
    ValidationRuleView,
)
from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.query_models import (
    AlternativeItinerary,
    AlternativeSearchRequirements,
    FlightStatus,
    ItineraryValidationResult,
    OperationalFlightStatus,
    RecoveryCaseQueueItem,
)
from travelops_recovery_agent.application.recommendation_models import (
    RecommendationResult,
)
from travelops_recovery_agent.domain.models import (
    CancelledFlightDetails,
    DelayedFlightDetails,
    Flight,
    MissedConnectionDetails,
    RecoveryCaseId,
)

logger = logging.getLogger(__name__)


class RecoveryQueryService(Protocol):
    def recommend(self, case_id: str) -> RecommendationResult: ...

    def list_recovery_cases(self) -> tuple[RecoveryCaseQueueItem, ...]: ...

    def get_recovery_case(
        self, case_id: RecoveryCaseId
    ) -> CompleteRecoveryCase | None: ...

    def get_flight_status(self, flight_id: str) -> FlightStatus | None: ...

    def search_alternative_itineraries(
        self, requirements: AlternativeSearchRequirements
    ) -> tuple[AlternativeItinerary, ...]: ...

    def validate_itinerary(
        self, flight_ids: tuple[str, ...]
    ) -> ItineraryValidationResult: ...


def get_recovery_query_service() -> RecoveryQueryService:
    """Return a safe sentinel unless the composition root provides a service."""

    return cast(RecoveryQueryService, _UnavailableRecoveryQueryService())


class _UnavailableRecoveryQueryService:
    """Delay configuration failure so routes can return safe JSON."""

    def __getattr__(self, _: str) -> object:
        raise RuntimeError("recovery query service is not configured")


RecoveryServiceDependency = Annotated[
    RecoveryQueryService, Depends(get_recovery_query_service)
]


def create_recovery_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["recovery"])

    @router.get("/recovery-cases", response_model=RecoveryCaseQueueView)
    def list_recovery_cases(
        service: RecoveryServiceDependency,
    ) -> RecoveryCaseQueueView | JSONResponse:
        try:
            return RecoveryCaseQueueView(
                cases=tuple(_queue_view(item) for item in service.list_recovery_cases())
            )
        except Exception:
            return _unavailable()

    @router.get(
        "/recovery-cases/{case_id}",
        response_model=RecoveryCaseWorkspaceView,
    )
    def get_recovery_case(
        case_id: RecoveryCaseId,
        service: RecoveryServiceDependency,
    ) -> RecoveryCaseWorkspaceView | JSONResponse:
        try:
            complete_case = service.get_recovery_case(case_id)
            if complete_case is None:
                return _not_found(case_id)
            return _workspace_view(complete_case, service)
        except Exception:
            return _unavailable()

    @router.get(
        "/recovery-cases/{case_id}/recommendation",
        response_model=RecommendationResult,
    )
    def get_recommendation(
        case_id: RecoveryCaseId,
        service: RecoveryServiceDependency,
    ) -> RecommendationResult | JSONResponse:
        try:
            if service.get_recovery_case(case_id) is None:
                return _not_found(case_id)
            return service.recommend(case_id)
        except Exception:
            return _unavailable()

    @router.post(
        "/alternative-itineraries/search",
        response_model=AlternativeSearchView,
    )
    def search_alternatives(
        request: AlternativeSearchRequest,
        service: RecoveryServiceDependency,
    ) -> AlternativeSearchView | JSONResponse:
        try:
            complete_case = service.get_recovery_case(request.case_id)
            if complete_case is None:
                return _not_found(request.case_id)
            first, last = complete_case.flights[0], complete_case.flights[-1]
            candidates = service.search_alternative_itineraries(
                AlternativeSearchRequirements(
                    origin=first.origin,
                    destination=last.destination,
                    earliest_departure=request.earliest_departure,
                    latest_arrival=request.latest_arrival,
                    max_connections=request.max_connections,
                )
            )
            return AlternativeSearchView(
                case_id=request.case_id,
                route=RecoveryCaseRouteView(
                    origin=first.origin, destination=last.destination
                ),
                passenger_count=len(complete_case.passengers),
                candidates=tuple(_candidate_view(item) for item in candidates),
            )
        except Exception:
            return _unavailable()

    @router.post("/itineraries/validate", response_model=ItineraryValidationView)
    def validate_itinerary(
        request: ItineraryValidationRequest,
        service: RecoveryServiceDependency,
    ) -> ItineraryValidationView | JSONResponse:
        try:
            if service.get_recovery_case(request.case_id) is None:
                return _not_found(request.case_id)
            result = service.validate_itinerary(request.flight_ids)
            rules = (
                *(
                    ValidationRuleView(
                        rule=item.rule, status=item.status, reason=item.reason
                    )
                    for item in result.rules
                ),
                ValidationRuleView(
                    rule="minimum_connection_policy",
                    status="deferred",
                    reason=(
                        "The manual schedule explorer does not certify a recovery; "
                        "the recommendation contract evaluates this rule."
                    ),
                ),
                ValidationRuleView(
                    rule="seat_inventory",
                    status="deferred",
                    reason=(
                        "The manual schedule explorer does not certify inventory; "
                        "the recommendation contract evaluates stored evidence."
                    ),
                ),
                ValidationRuleView(
                    rule="ticket_rules",
                    status="deferred",
                    reason=(
                        "The manual schedule explorer does not certify ticket rules; "
                        "the recommendation contract evaluates stored evidence."
                    ),
                ),
            )
            return ItineraryValidationView(
                case_id=request.case_id,
                candidate_id=request.candidate_id,
                flight_ids=result.flight_ids,
                structurally_valid=result.valid,
                rules=rules,
            )
        except Exception:
            return _unavailable()

    return router


def _queue_view(item: RecoveryCaseQueueItem) -> RecoveryCaseQueueItemView:
    first, last = item.itinerary[0], item.itinerary[-1]
    status = item.affected_flight_status
    return RecoveryCaseQueueItemView(
        case_id=item.recovery_case.id,
        title=item.recovery_case.title,
        booking_id=item.booking.id,
        route=RecoveryCaseRouteView(origin=first.origin, destination=last.destination),
        passenger_count=item.passenger_count,
        disruption_type=item.disruption.details.type,
        affected_flight_id=item.disruption.affected_flight_id,
        occurred_at=item.disruption.occurred_at,
        operational_status=status.status,
        delay_minutes=status.delay_minutes,
        cancellation_reason=status.cancellation_reason,
        journey_departure=first.scheduled_departure,
        journey_arrival=last.scheduled_arrival,
    )


def _workspace_view(
    complete_case: CompleteRecoveryCase,
    service: RecoveryQueryService,
) -> RecoveryCaseWorkspaceView:
    disruption = complete_case.disruption
    details = disruption.details
    status_by_flight = {
        flight.id: service.get_flight_status(flight.id)
        for flight in complete_case.flights
    }
    itinerary = tuple(
        ItinerarySegmentView(
            segment_id=segment.id,
            sequence=segment.sequence,
            flight_id=flight.id,
            service=f"{flight.carrier_code} {flight.flight_number}",
            origin=flight.origin,
            destination=flight.destination,
            scheduled_departure=flight.scheduled_departure,
            scheduled_arrival=flight.scheduled_arrival,
            operational_status=(
                status_by_flight[flight.id] or _scheduled(flight)
            ).status,
            delay_minutes=(
                status_by_flight[flight.id] or _scheduled(flight)
            ).delay_minutes,
            cancellation_reason=(
                status_by_flight[flight.id] or _scheduled(flight)
            ).cancellation_reason,
            affected=flight.id == disruption.affected_flight_id,
        )
        for segment, flight in zip(
            complete_case.booking.segments, complete_case.flights, strict=True
        )
    )
    first, last = complete_case.flights[0], complete_case.flights[-1]
    return RecoveryCaseWorkspaceView(
        case_id=complete_case.recovery_case.id,
        title=complete_case.recovery_case.title,
        booking_id=complete_case.booking.id,
        passengers=tuple(
            PassengerView(
                passenger_id=passenger.id,
                display_name=f"{passenger.given_name} {passenger.family_name}",
            )
            for passenger in complete_case.passengers
        ),
        itinerary=itinerary,
        disruption=DisruptionEvidenceView(
            disruption_id=disruption.id,
            disruption_type=details.type,
            affected_flight_id=disruption.affected_flight_id,
            affected_segment_id=disruption.affected_segment_id,
            occurred_at=disruption.occurred_at,
            delay_minutes=(
                details.delay_minutes
                if isinstance(details, DelayedFlightDetails)
                else None
            ),
            cancellation_reason=(
                details.reason if isinstance(details, CancelledFlightDetails) else None
            ),
            arriving_flight_id=(
                details.arriving_flight_id
                if isinstance(details, MissedConnectionDetails)
                else None
            ),
            missed_flight_id=(
                details.missed_flight_id
                if isinstance(details, MissedConnectionDetails)
                else None
            ),
        ),
        policy=PolicyEvidenceView(
            policy_id=complete_case.policy.id,
            name=complete_case.policy.name,
            summary=complete_case.policy.summary,
            applicable_types=complete_case.policy.applicable_types,
            rebooking_window_hours=complete_case.policy.rebooking_window_hours,
            allows_next_day=complete_case.policy.allows_next_day,
        ),
        search_defaults=AlternativeSearchDefaultsView(
            origin=first.origin,
            destination=last.destination,
            earliest_departure=disruption.occurred_at,
            latest_arrival=disruption.occurred_at
            + timedelta(hours=complete_case.policy.rebooking_window_hours),
            passenger_count=len(complete_case.passengers),
        ),
        recommendation=service.recommend(complete_case.recovery_case.id),
    )


def _scheduled(flight: Flight) -> FlightStatus:
    return FlightStatus(
        flight=flight,
        status=OperationalFlightStatus.SCHEDULED,
        delay_minutes=None,
        cancellation_reason=None,
        related_disruptions=(),
    )


def _candidate_view(item: AlternativeItinerary) -> AlternativeCandidateView:
    return AlternativeCandidateView(
        candidate_id="CAND-" + "-".join(flight.id for flight in item.flights),
        segments=tuple(
            CandidateSegmentView(
                flight_id=flight.id,
                service=f"{flight.carrier_code} {flight.flight_number}",
                origin=flight.origin,
                destination=flight.destination,
                scheduled_departure=flight.scheduled_departure,
                scheduled_arrival=flight.scheduled_arrival,
            )
            for flight in item.flights
        ),
        connection_minutes=item.connection_minutes,
        scheduled_duration_minutes=int(
            (
                item.flights[-1].scheduled_arrival - item.flights[0].scheduled_departure
            ).total_seconds()
            // 60
        ),
    )


def _not_found(case_id: str) -> JSONResponse:
    error = ApiErrorView(
        error=ApiErrorDetail(
            code="not_found",
            message=f"Recovery case {case_id} was not found.",
            retryable=False,
        )
    )
    return JSONResponse(status_code=404, content=error.model_dump(mode="json"))


def _unavailable() -> JSONResponse:
    logger.error("recovery_api_dependency_failed")
    error = ApiErrorView(
        error=ApiErrorDetail(
            code="service_unavailable",
            message="Recovery data is temporarily unavailable.",
            retryable=True,
        )
    )
    return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
