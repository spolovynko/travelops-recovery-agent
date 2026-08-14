"""Deterministic candidate validation and explainable recommendation ranking."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from travelops_recovery_agent.application.query_models import (
    AvailabilityEvidence,
    FlightStatus,
    OperationalFlightStatus,
    TicketRuleEvidence,
)
from travelops_recovery_agent.application.recommendation_models import (
    EvidenceCompleteness,
    EvidenceKind,
    EvidenceReference,
    OptionValidation,
    RankingInputs,
    RecommendationOption,
    RecommendationOutcome,
    RecommendationResult,
    RecommendationRule,
    RecommendationSegment,
    ValidationCheck,
    ValidationStatus,
)
from travelops_recovery_agent.application.services import (
    RecoveryDataUnitOfWorkFactory,
)
from travelops_recovery_agent.domain.models import (
    CancelledFlightDetails,
    DelayedFlightDetails,
    Disruption,
    Flight,
)

MINIMUM_CONNECTION_MINUTES = 45
RANKING_METHOD = (
    "lexicographic: earliest operational arrival, fewest connections, "
    "least connection waiting, greatest seat surplus, stable option id"
)


@dataclass(frozen=True)
class CandidateItinerary:
    flight_ids: tuple[str, ...]

    @property
    def option_id(self) -> str:
        return "REC-" + "-".join(self.flight_ids)


def _flight_status(flight: Flight, disruptions: tuple[Disruption, ...]) -> FlightStatus:
    cancellations = [
        item.details.reason
        for item in disruptions
        if isinstance(item.details, CancelledFlightDetails)
    ]
    delays = [
        item.details.delay_minutes
        for item in disruptions
        if isinstance(item.details, DelayedFlightDetails)
    ]
    if cancellations:
        status = OperationalFlightStatus.CANCELLED
        delay_minutes = None
        cancellation_reason = cancellations[0]
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
        related_disruptions=disruptions,
    )


def _check(
    rule: RecommendationRule,
    status: ValidationStatus,
    summary: str,
    *evidence_ids: str,
) -> ValidationCheck:
    return ValidationCheck(
        rule=rule,
        status=status,
        summary=summary,
        evidence_ids=tuple(evidence_ids),
    )


def _effective_times(status: FlightStatus) -> tuple[datetime, datetime]:
    delay = timedelta(minutes=status.delay_minutes or 0)
    return (
        status.flight.scheduled_departure + delay,
        status.flight.scheduled_arrival + delay,
    )


def validate_recommendation_option(
    candidate: CandidateItinerary,
    *,
    flights_by_id: Mapping[str, Flight],
    statuses_by_id: Mapping[str, FlightStatus],
    availability_by_id: Mapping[str, AvailabilityEvidence],
    ticket_rule: TicketRuleEvidence | None,
    passenger_count: int,
    policy_id: str,
    policy_allows_next_day: bool,
    policy_deadline: datetime,
    disruption_date: datetime,
) -> RecommendationOption:
    """Evaluate every required rule without converting missing evidence to a pass."""

    evidence: dict[str, EvidenceReference] = {}
    missing = [item for item in candidate.flight_ids if item not in flights_by_id]
    if missing:
        missing_checks = (
            _check(
                RecommendationRule.FLIGHTS_EXIST,
                ValidationStatus.FAILED,
                "Stored flights are missing: " + ", ".join(missing),
            ),
            *(
                _check(
                    rule, ValidationStatus.NOT_EVALUATED, "All flights must exist first"
                )
                for rule in RecommendationRule
                if rule is not RecommendationRule.FLIGHTS_EXIST
            ),
        )
        reasons = tuple(
            check.summary
            for check in missing_checks
            if check.status is ValidationStatus.FAILED
        )
        return RecommendationOption(
            option_id=candidate.option_id,
            segments=(),
            validation=OptionValidation(
                valid=False,
                evidence_complete=True,
                checks=missing_checks,
                rejection_reasons=reasons,
            ),
            evidence_references=(),
        )

    flights = tuple(flights_by_id[item] for item in candidate.flight_ids)
    for flight in flights:
        evidence[f"flight:{flight.id}"] = EvidenceReference(
            evidence_id=f"flight:{flight.id}",
            kind=EvidenceKind.STORED_FLIGHT,
            source="repository:flights",
            summary=f"Stored flight {flight.id} is {flight.origin} to {flight.destination}.",
        )
        evidence[f"schedule:{flight.id}"] = EvidenceReference(
            evidence_id=f"schedule:{flight.id}",
            kind=EvidenceKind.SCHEDULE,
            source="repository:flights",
            summary=(
                f"Scheduled {flight.scheduled_departure.isoformat()} to "
                f"{flight.scheduled_arrival.isoformat()}."
            ),
        )

    flight_ids = tuple(f"flight:{item.id}" for item in flights)
    checks: list[ValidationCheck] = [
        _check(
            RecommendationRule.FLIGHTS_EXIST,
            ValidationStatus.PASSED,
            "Every segment exists in stored flight data.",
            *flight_ids,
        )
    ]

    disconnected = [
        f"{first.id}->{second.id}"
        for first, second in pairwise(flights)
        if first.destination != second.origin
    ]
    checks.append(
        _check(
            RecommendationRule.ROUTE_CONTINUITY,
            ValidationStatus.FAILED if disconnected else ValidationStatus.PASSED,
            (
                "Disconnected flight pairs: " + ", ".join(disconnected)
                if disconnected
                else "Every segment continues from the preceding destination."
            ),
            *flight_ids,
        )
    )

    missing_status = [item.id for item in flights if item.id not in statuses_by_id]
    statuses = tuple(
        statuses_by_id[item.id] for item in flights if item.id in statuses_by_id
    )
    for status in statuses:
        evidence[f"status:{status.flight.id}"] = EvidenceReference(
            evidence_id=f"status:{status.flight.id}",
            kind=EvidenceKind.FLIGHT_STATUS,
            source="repository:flights+disruptions",
            summary=f"Current stored status is {status.status.value}.",
        )
    cancelled = [
        status.flight.id
        for status in statuses
        if status.status is OperationalFlightStatus.CANCELLED
    ]
    if missing_status:
        checks.append(
            _check(
                RecommendationRule.STORED_FLIGHT_STATUS,
                ValidationStatus.MISSING_EVIDENCE,
                "Current status evidence is missing for: " + ", ".join(missing_status),
            )
        )
    else:
        checks.append(
            _check(
                RecommendationRule.STORED_FLIGHT_STATUS,
                ValidationStatus.FAILED if cancelled else ValidationStatus.PASSED,
                (
                    "Cancelled flights cannot be recommended: " + ", ".join(cancelled)
                    if cancelled
                    else "Every stored flight has a non-cancelled current status."
                ),
                *(f"status:{item.id}" for item in flights),
            )
        )

    effective = tuple(_effective_times(item) for item in statuses)
    overlapping = [
        f"{flights[index].id}->{flights[index + 1].id}"
        for index in range(max(0, len(effective) - 1))
        if effective[index + 1][0] < effective[index][1]
    ]
    if missing_status:
        checks.append(
            _check(
                RecommendationRule.FLIGHT_AND_CONNECTION_TIMES,
                ValidationStatus.NOT_EVALUATED,
                "Operational timing requires current status for every flight.",
            )
        )
    else:
        checks.append(
            _check(
                RecommendationRule.FLIGHT_AND_CONNECTION_TIMES,
                ValidationStatus.FAILED if overlapping else ValidationStatus.PASSED,
                (
                    "Connections overlap after operational delays: "
                    + ", ".join(overlapping)
                    if overlapping
                    else "Flight durations and operational connection times are chronological."
                ),
                *(f"schedule:{item.id}" for item in flights),
                *(f"status:{item.id}" for item in flights),
            )
        )

    connection_minutes = tuple(
        int((effective[index + 1][0] - effective[index][1]).total_seconds() // 60)
        for index in range(max(0, len(effective) - 1))
    )
    for airport in (item.destination for item in flights[:-1]):
        evidence[f"mct:{airport}:{MINIMUM_CONNECTION_MINUTES}"] = EvidenceReference(
            evidence_id=f"mct:{airport}:{MINIMUM_CONNECTION_MINUTES}",
            kind=EvidenceKind.MINIMUM_CONNECTION_TIME,
            source="application-rule:synthetic-mct-v1",
            summary=f"Synthetic minimum connection time at {airport} is {MINIMUM_CONNECTION_MINUTES} minutes.",
        )
    short = [
        str(item) for item in connection_minutes if item < MINIMUM_CONNECTION_MINUTES
    ]
    if missing_status:
        checks.append(
            _check(
                RecommendationRule.MINIMUM_CONNECTION_TIME,
                ValidationStatus.NOT_EVALUATED,
                "Minimum connection time requires operational timing evidence.",
            )
        )
    else:
        checks.append(
            _check(
                RecommendationRule.MINIMUM_CONNECTION_TIME,
                ValidationStatus.FAILED if short else ValidationStatus.PASSED,
                (
                    "Connection minutes below the 45-minute minimum: "
                    + ", ".join(short)
                    if short
                    else "Every connection meets the 45-minute synthetic minimum."
                ),
                *(
                    f"mct:{item.destination}:{MINIMUM_CONNECTION_MINUTES}"
                    for item in flights[:-1]
                ),
                *(f"schedule:{item.id}" for item in flights),
            )
        )

    missing_inventory = [
        item.id for item in flights if item.id not in availability_by_id
    ]
    for item in flights:
        availability = availability_by_id.get(item.id)
        if availability is not None:
            evidence[f"availability:{item.id}"] = EvidenceReference(
                evidence_id=f"availability:{item.id}",
                kind=EvidenceKind.SEAT_AVAILABILITY,
                source=availability.source,
                summary=f"{availability.available_seats} seats are available on {item.id}.",
                observed_at=availability.observed_at,
            )
    insufficient = [
        f"{item.id} ({availability_by_id[item.id].available_seats})"
        for item in flights
        if item.id in availability_by_id
        and availability_by_id[item.id].available_seats < passenger_count
    ]
    if missing_inventory:
        checks.append(
            _check(
                RecommendationRule.GROUP_SEAT_AVAILABILITY,
                ValidationStatus.MISSING_EVIDENCE,
                "Seat evidence is missing for: " + ", ".join(missing_inventory),
                *(
                    f"availability:{item.id}"
                    for item in flights
                    if item.id in availability_by_id
                ),
            )
        )
    else:
        checks.append(
            _check(
                RecommendationRule.GROUP_SEAT_AVAILABILITY,
                ValidationStatus.FAILED if insufficient else ValidationStatus.PASSED,
                (
                    f"The complete group of {passenger_count} cannot fit on: "
                    + ", ".join(insufficient)
                    if insufficient
                    else f"Every segment has seats for all {passenger_count} passengers."
                ),
                *(f"availability:{item.id}" for item in flights),
            )
        )

    evidence[f"policy:{policy_id}"] = EvidenceReference(
        evidence_id=f"policy:{policy_id}",
        kind=EvidenceKind.DISRUPTION_POLICY,
        source="repository:disruption_policies",
        summary=f"Recovery must arrive by {policy_deadline.isoformat()}.",
    )
    if ticket_rule is None:
        checks.append(
            _check(
                RecommendationRule.TICKET_AND_REBOOKING_RULES,
                ValidationStatus.MISSING_EVIDENCE,
                "Stored ticket and rebooking evidence is missing for this booking.",
                f"policy:{policy_id}",
            )
        )
        ticket_compatible = False
    else:
        evidence[f"ticket-rule:{ticket_rule.booking_id}"] = EvidenceReference(
            evidence_id=f"ticket-rule:{ticket_rule.booking_id}",
            kind=EvidenceKind.TICKET_RULE,
            source=ticket_rule.source,
            summary=(
                f"Rebooking allowed={ticket_rule.rebooking_allowed}; carrier "
                f"{ticket_rule.allowed_carrier_code}; maximum "
                f"{ticket_rule.max_connections} connections."
            ),
            observed_at=ticket_rule.observed_at,
        )
        violations: list[str] = []
        if not ticket_rule.rebooking_allowed:
            violations.append("the ticket is not marked rebookable")
        if any(
            item.carrier_code != ticket_rule.allowed_carrier_code for item in flights
        ):
            violations.append("one or more carriers are not ticket-compatible")
        if len(flights) - 1 > ticket_rule.max_connections:
            violations.append("the ticket connection limit is exceeded")
        operational_arrival = (
            effective[-1][1] if effective else flights[-1].scheduled_arrival
        )
        if operational_arrival > policy_deadline:
            violations.append("arrival falls outside the disruption-policy window")
        if (
            not policy_allows_next_day
            and operational_arrival.astimezone(UTC).date()
            != disruption_date.astimezone(UTC).date()
        ):
            violations.append("next-day recovery is not allowed")
        ticket_compatible = not violations
        checks.append(
            _check(
                RecommendationRule.TICKET_AND_REBOOKING_RULES,
                ValidationStatus.FAILED if violations else ValidationStatus.PASSED,
                "; ".join(violations)
                if violations
                else "Ticket and disruption-policy rules permit this itinerary.",
                f"ticket-rule:{ticket_rule.booking_id}",
                f"policy:{policy_id}",
            )
        )

    rejection_reasons = tuple(
        item.summary
        for item in checks
        if item.status in {ValidationStatus.FAILED, ValidationStatus.MISSING_EVIDENCE}
    )
    valid = all(item.status is ValidationStatus.PASSED for item in checks)
    complete = all(
        item.status is not ValidationStatus.MISSING_EVIDENCE for item in checks
    )
    segments = tuple(
        RecommendationSegment(
            flight_id=flight.id,
            service=f"{flight.carrier_code}{flight.flight_number}",
            origin=flight.origin,
            destination=flight.destination,
            scheduled_departure=flight.scheduled_departure,
            scheduled_arrival=flight.scheduled_arrival,
            operational_departure=_effective_times(statuses_by_id[flight.id])[0]
            if flight.id in statuses_by_id
            else flight.scheduled_departure,
            operational_arrival=_effective_times(statuses_by_id[flight.id])[1]
            if flight.id in statuses_by_id
            else flight.scheduled_arrival,
            status=statuses_by_id[flight.id].status.value
            if flight.id in statuses_by_id
            else "unknown",
            available_seats=(
                availability_by_id[flight.id].available_seats
                if flight.id in availability_by_id
                else None
            ),
        )
        for flight in flights
    )
    ranking_inputs: RankingInputs | None = None
    tradeoffs: tuple[str, ...] = ()
    if valid:
        minimum_seats = min(
            item.available_seats
            for item in availability_by_id.values()
            if item.flight_id in candidate.flight_ids
        )
        ranking_inputs = RankingInputs(
            arrival_time=segments[-1].operational_arrival,
            connection_count=len(segments) - 1,
            total_wait_minutes=sum(connection_minutes),
            minimum_available_seats=minimum_seats,
            passenger_count=passenger_count,
            seat_surplus=minimum_seats - passenger_count,
            policy_compatible=True,
            ticket_compatible=ticket_compatible,
        )
        tradeoffs = (
            f"Arrives at {ranking_inputs.arrival_time.isoformat()}.",
            f"Uses {ranking_inputs.connection_count} connection(s) with {ranking_inputs.total_wait_minutes} waiting minute(s).",
            f"Leaves a minimum seat surplus of {ranking_inputs.seat_surplus} for the complete group.",
        )
    return RecommendationOption(
        option_id=candidate.option_id,
        segments=segments,
        validation=OptionValidation(
            valid=valid,
            evidence_complete=complete,
            checks=tuple(checks),
            rejection_reasons=rejection_reasons,
        ),
        evidence_references=tuple(evidence.values()),
        ranking_inputs=ranking_inputs,
        tradeoffs=tradeoffs,
    )


class RecommendationService:
    """Build one reproducible, repository-grounded recommendation snapshot."""

    def __init__(self, unit_of_work_factory: RecoveryDataUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def recommend(self, case_id: str) -> RecommendationResult:
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repository
            complete_case = repository.get_complete_case(case_id)
            if complete_case is None:
                raise LookupError(f"recovery case {case_id} was not found")
            first, last = complete_case.flights[0], complete_case.flights[-1]
            deadline = complete_case.disruption.occurred_at + timedelta(
                hours=complete_case.policy.rebooking_window_hours
            )
            flights = repository.list_flights_in_window(
                complete_case.disruption.occurred_at,
                deadline,
            )
            candidates = self._candidates(flights, first.origin, last.destination)
            candidate_ids = tuple(
                flight_id for item in candidates for flight_id in item.flight_ids
            )
            unique_ids = tuple(dict.fromkeys(candidate_ids))
            stored = repository.get_flights_by_ids(unique_ids)
            status_values = {
                item: repository.get_flight_with_disruptions(item)
                for item in unique_ids
            }
            availability = repository.get_availability_by_flight_ids(unique_ids)
            ticket_rule = repository.get_ticket_rule(complete_case.booking.id)

        flights_by_id = {item.id: item for item in stored}
        statuses = {
            flight_id: _flight_status(value.flight, value.disruptions)
            for flight_id, value in status_values.items()
            if value is not None
        }
        availability_by_id = {item.flight_id: item for item in availability}
        options = tuple(
            validate_recommendation_option(
                item,
                flights_by_id=flights_by_id,
                statuses_by_id=statuses,
                availability_by_id=availability_by_id,
                ticket_rule=ticket_rule,
                passenger_count=len(complete_case.passengers),
                policy_id=complete_case.policy.id,
                policy_allows_next_day=complete_case.policy.allows_next_day,
                policy_deadline=deadline,
                disruption_date=complete_case.disruption.occurred_at,
            )
            for item in candidates
        )
        ranked = sorted(
            (item for item in options if item.validation.valid),
            key=lambda item: (
                (
                    item.ranking_inputs.arrival_time,
                    item.ranking_inputs.connection_count,
                    item.ranking_inputs.total_wait_minutes,
                    -item.ranking_inputs.seat_surplus,
                    item.option_id,
                )
                if item.ranking_inputs is not None
                else (datetime.max.replace(tzinfo=UTC), 99, 99_999, 0, item.option_id)
            ),
        )
        ranked = [
            item.model_copy(
                update={
                    "ranking_inputs": item.ranking_inputs.model_copy(
                        update={"rank_position": index}
                    )
                    if item.ranking_inputs is not None
                    else None
                }
            )
            for index, item in enumerate(ranked, start=1)
        ]
        ranked_by_id = {item.option_id: item for item in ranked}
        option_results = tuple(
            ranked_by_id.get(item.option_id, item) for item in options
        )
        all_evidence = {
            evidence.evidence_id: evidence
            for item in option_results
            for evidence in item.evidence_references
        }
        missing_evidence = any(
            not item.validation.evidence_complete for item in options
        )
        if ranked:
            outcome = RecommendationOutcome.RECOMMENDED
            completeness = (
                EvidenceCompleteness.PARTIAL
                if missing_evidence
                else EvidenceCompleteness.COMPLETE
            )
            escalation = None
        elif missing_evidence:
            outcome = RecommendationOutcome.INSUFFICIENT_EVIDENCE
            completeness = EvidenceCompleteness.INSUFFICIENT
            escalation = (
                "No itinerary has complete evidence for every required validation rule."
            )
        else:
            outcome = RecommendationOutcome.NO_SAFE_OPTION
            completeness = EvidenceCompleteness.COMPLETE
            escalation = (
                "No generated itinerary passed every deterministic safety rule."
                if candidates
                else "No itinerary was found inside the permitted recovery window."
            )
        return RecommendationResult(
            case_id=case_id,
            outcome=outcome,
            recommended_itinerary=ranked[0] if ranked else None,
            other_validated_options=tuple(ranked[1:]),
            option_results=option_results,
            evidence_references=tuple(all_evidence.values()),
            evidence_completeness=completeness,
            escalation_reason=escalation,
            ranking_method=RANKING_METHOD,
        )

    @staticmethod
    def _candidates(
        flights: tuple[Flight, ...], origin: str, destination: str
    ) -> tuple[CandidateItinerary, ...]:
        ordered = tuple(
            sorted(
                flights,
                key=lambda item: (
                    item.scheduled_departure,
                    item.scheduled_arrival,
                    item.id,
                ),
            )
        )
        results = [
            CandidateItinerary((item.id,))
            for item in ordered
            if item.origin == origin and item.destination == destination
        ]
        for first in ordered:
            if first.origin != origin:
                continue
            for second in ordered:
                if (
                    first.id == second.id
                    or first.destination != second.origin
                    or second.destination != destination
                    or second.scheduled_departure < first.scheduled_arrival
                ):
                    continue
                results.append(CandidateItinerary((first.id, second.id)))
        unique = {item.option_id: item for item in results}
        return tuple(unique[key] for key in sorted(unique))
