"""Read-only application services for operational tools."""

from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.query_models import (
    AlternativeItinerary,
    AlternativeSearchRequirements,
    CompleteBooking,
    FlightStatus,
    ItineraryValidationResult,
    OperationalFlightStatus,
    RecoveryCaseQueueItem,
    ResolvedDisruptionPolicy,
)
from travelops_recovery_agent.application.services import (
    RecoveryDataUnitOfWorkFactory,
)
from travelops_recovery_agent.domain.itinerary_validation import (
    validate_candidate_itinerary,
)
from travelops_recovery_agent.domain.models import (
    BookingId,
    CancelledFlightDetails,
    DelayedFlightDetails,
    Disruption,
    DisruptionId,
    Flight,
    FlightId,
    RecoveryCaseId,
)


class OperationalQueryService:
    """Coordinate narrow read-only operational queries."""

    def __init__(
        self,
        unit_of_work_factory: RecoveryDataUnitOfWorkFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_booking(self, booking_id: BookingId) -> CompleteBooking | None:
        """Return one complete booking without exposing persistence objects."""
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.get_complete_booking(booking_id)

    def list_recovery_cases(self) -> tuple[RecoveryCaseQueueItem, ...]:
        """Return deterministic application facts for the disruption queue."""

        with self._unit_of_work_factory() as unit_of_work:
            complete_cases = unit_of_work.repository.list_complete_cases()

        return tuple(
            self._build_queue_item(complete_case) for complete_case in complete_cases
        )

    def get_recovery_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        """Return one complete case without exposing persistence objects."""

        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.get_complete_case(case_id)

    def _build_queue_item(
        self,
        complete_case: CompleteRecoveryCase,
    ) -> RecoveryCaseQueueItem:
        """Build one queue item from validated stored business facts."""

        disruption = complete_case.disruption
        affected_flight = next(
            flight
            for flight in complete_case.flights
            if flight.id == disruption.affected_flight_id
        )

        return RecoveryCaseQueueItem(
            recovery_case=complete_case.recovery_case,
            booking=complete_case.booking,
            passenger_count=len(complete_case.passengers),
            itinerary=complete_case.flights,
            disruption=disruption,
            affected_flight_status=self._build_flight_status(
                affected_flight,
                (disruption,),
            ),
        )

    def get_flight_status(self, flight_id: FlightId) -> FlightStatus | None:
        """Derive synthetic operational status from stored disruption data."""

        with self._unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.repository.get_flight_with_disruptions(flight_id)

        if stored is None:
            return None

        return self._build_flight_status(
            stored.flight,
            stored.disruptions,
        )

    @staticmethod
    def _build_flight_status(
        flight: Flight,
        disruptions: tuple[Disruption, ...],
    ) -> FlightStatus:
        """Build deterministic status from stored flight and disruption facts."""

        ordered_disruptions = tuple(
            sorted(
                disruptions,
                key=lambda item: (item.occurred_at, item.id),
            )
        )
        cancellation_reasons = [
            item.details.reason
            for item in ordered_disruptions
            if isinstance(item.details, CancelledFlightDetails)
        ]
        delays = [
            item.details.delay_minutes
            for item in ordered_disruptions
            if isinstance(item.details, DelayedFlightDetails)
        ]

        if cancellation_reasons:
            status = OperationalFlightStatus.CANCELLED
            delay_minutes = None
            cancellation_reason = cancellation_reasons[0]
        elif delays:
            status = OperationalFlightStatus.DELAYED
            delay_minutes = max(delays)
            cancellation_reason = None
        else:
            status = OperationalFlightStatus.SCHEDULED
            delay_minutes = None
            cancellation_reason = None

        return FlightStatus(
            flight=flight,
            status=status,
            delay_minutes=delay_minutes,
            cancellation_reason=cancellation_reason,
            related_disruptions=ordered_disruptions,
        )

    def get_disruption_policy_for_case(
        self,
        case_id: RecoveryCaseId,
    ) -> ResolvedDisruptionPolicy | None:
        """Resolve a structured policy through one recovery case."""

        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.get_disruption_policy_for_case(case_id)

    def get_disruption_policy_for_disruption(
        self,
        disruption_id: DisruptionId,
    ) -> ResolvedDisruptionPolicy | None:
        """Resolve a structured policy through one disruption."""

        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.get_disruption_policy_for_disruption(
                disruption_id
            )

    def search_alternative_itineraries(
        self,
        requirements: AlternativeSearchRequirements,
    ) -> tuple[AlternativeItinerary, ...]:
        """Build deterministic direct and one-connection candidates."""

        with self._unit_of_work_factory() as unit_of_work:
            flights = unit_of_work.repository.list_flights_in_window(
                requirements.earliest_departure,
                requirements.latest_arrival,
            )

        ordered_flights = tuple(
            sorted(
                flights,
                key=lambda item: (
                    item.scheduled_departure,
                    item.scheduled_arrival,
                    item.id,
                ),
            )
        )
        candidates: list[AlternativeItinerary] = [
            AlternativeItinerary(flights=(flight,), connection_minutes=())
            for flight in ordered_flights
            if flight.origin == requirements.origin
            and flight.destination == requirements.destination
        ]

        if requirements.max_connections == 1:
            for first in ordered_flights:
                if first.origin != requirements.origin:
                    continue
                for second in ordered_flights:
                    if (
                        second.id == first.id
                        or first.destination != second.origin
                        or second.destination != requirements.destination
                        or second.scheduled_departure < first.scheduled_arrival
                    ):
                        continue
                    connection_minutes = int(
                        (
                            second.scheduled_departure - first.scheduled_arrival
                        ).total_seconds()
                        // 60
                    )
                    candidates.append(
                        AlternativeItinerary(
                            flights=(first, second),
                            connection_minutes=(connection_minutes,),
                        )
                    )

        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.flights[-1].scheduled_arrival,
                    item.flights[0].scheduled_departure,
                    tuple(flight.id for flight in item.flights),
                ),
            )
        )

    def validate_itinerary(
        self,
        flight_ids: tuple[FlightId, ...],
    ) -> ItineraryValidationResult:
        """Validate trusted stored flight facts with fixed domain rules."""

        with self._unit_of_work_factory() as unit_of_work:
            flights = unit_of_work.repository.get_flights_by_ids(flight_ids)

        validation = validate_candidate_itinerary(
            flight_ids,
            {flight.id: flight for flight in flights},
        )
        return ItineraryValidationResult(
            flight_ids=flight_ids,
            valid=validation.valid,
            rules=validation.rules,
        )
