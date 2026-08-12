"""Deterministic validation rules for proposed flight itineraries."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from travelops_recovery_agent.domain.models import Flight


class ItineraryRule(StrEnum):
    """Rules currently enforceable from Phase 2 flight facts."""

    FLIGHTS_EXIST = "flights_exist"
    ROUTE_CONTINUITY = "route_continuity"
    CHRONOLOGICAL_ORDER = "chronological_order"


class RuleStatus(StrEnum):
    """Outcome of evaluating one deterministic itinerary rule."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class ItineraryRuleResult:
    """Structured result and reason for one itinerary rule."""

    rule: ItineraryRule
    status: RuleStatus
    reason: str


@dataclass(frozen=True)
class ItineraryValidation:
    """Overall validity derived only from evaluated deterministic rules."""

    valid: bool
    ordered_flights: tuple[Flight, ...]
    rules: tuple[ItineraryRuleResult, ...]


def validate_candidate_itinerary(
    requested_flight_ids: tuple[str, ...],
    flights_by_id: Mapping[str, Flight],
) -> ItineraryValidation:
    """Validate existence, route continuity, and chronological ordering."""

    missing_ids = tuple(
        flight_id
        for flight_id in requested_flight_ids
        if flight_id not in flights_by_id
    )
    if missing_ids:
        return ItineraryValidation(
            valid=False,
            ordered_flights=(),
            rules=(
                ItineraryRuleResult(
                    rule=ItineraryRule.FLIGHTS_EXIST,
                    status=RuleStatus.FAILED,
                    reason="missing stored flights: " + ", ".join(missing_ids),
                ),
                ItineraryRuleResult(
                    rule=ItineraryRule.ROUTE_CONTINUITY,
                    status=RuleStatus.NOT_EVALUATED,
                    reason="route continuity requires every flight",
                ),
                ItineraryRuleResult(
                    rule=ItineraryRule.CHRONOLOGICAL_ORDER,
                    status=RuleStatus.NOT_EVALUATED,
                    reason="chronological order requires every flight",
                ),
            ),
        )

    ordered_flights = tuple(flights_by_id[item] for item in requested_flight_ids)
    disconnected_pairs = tuple(
        (previous.id, current.id)
        for previous, current in pairwise(ordered_flights)
        if previous.destination != current.origin
    )
    overlapping_pairs = tuple(
        (previous.id, current.id)
        for previous, current in pairwise(ordered_flights)
        if current.scheduled_departure < previous.scheduled_arrival
    )

    route_rule = ItineraryRuleResult(
        rule=ItineraryRule.ROUTE_CONTINUITY,
        status=(RuleStatus.FAILED if disconnected_pairs else RuleStatus.PASSED),
        reason=(
            "disconnected flight pairs: "
            + ", ".join(f"{first}->{second}" for first, second in disconnected_pairs)
            if disconnected_pairs
            else "every consecutive flight uses the preceding destination"
        ),
    )
    chronological_rule = ItineraryRuleResult(
        rule=ItineraryRule.CHRONOLOGICAL_ORDER,
        status=(RuleStatus.FAILED if overlapping_pairs else RuleStatus.PASSED),
        reason=(
            "overlapping flight pairs: "
            + ", ".join(f"{first}->{second}" for first, second in overlapping_pairs)
            if overlapping_pairs
            else "every consecutive flight departs after the preceding arrival"
        ),
    )
    rules = (
        ItineraryRuleResult(
            rule=ItineraryRule.FLIGHTS_EXIST,
            status=RuleStatus.PASSED,
            reason="every requested flight exists in stored business data",
        ),
        route_rule,
        chronological_rule,
    )
    return ItineraryValidation(
        valid=all(rule.status is RuleStatus.PASSED for rule in rules),
        ordered_flights=ordered_flights,
        rules=rules,
    )
