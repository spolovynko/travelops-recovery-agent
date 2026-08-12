"""Direct command-line runner for read-only operational tools."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Protocol, cast

from pydantic import BaseModel, ValidationError

from travelops_recovery_agent.application.query_services import (
    OperationalQueryService,
)
from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import (
    DatabaseConfigurationError,
    create_database_engine,
    create_session_factory,
)
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)
from travelops_recovery_agent.tools.adapters import (
    GetBookingTool,
    GetDisruptionPolicyTool,
    GetFlightStatusTool,
    SearchAlternativeItinerariesTool,
    ValidateItineraryTool,
)
from travelops_recovery_agent.tools.contracts import (
    ToolExecutionContext,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS


class Disposable(Protocol):
    """Small cleanup contract used by the command-line composition root."""

    def dispose(self) -> None:
        """Release owned resources."""


@dataclass(frozen=True)
class ToolRuntime:
    """Concrete read-only adapters available to the command-line runner."""

    get_booking: GetBookingTool
    get_flight_status: GetFlightStatusTool
    get_disruption_policy: GetDisruptionPolicyTool
    search_alternative_itineraries: SearchAlternativeItinerariesTool
    validate_itinerary: ValidateItineraryTool


def build_parser() -> argparse.ArgumentParser:
    """Build the stable manual interface for schema discovery and tool calls."""

    parser = argparse.ArgumentParser(description="Run TravelOps read-only tools.")
    parser.add_argument("--actor-id", default="manual-operator")
    parser.add_argument("--correlation-id", default="manual-tool-call")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Print every stable tool schema.")

    booking = commands.add_parser("get-booking")
    booking.add_argument("booking_id")

    flight = commands.add_parser("get-flight-status")
    flight.add_argument("flight_id")

    policy = commands.add_parser("get-disruption-policy")
    policy_reference = policy.add_mutually_exclusive_group(required=True)
    policy_reference.add_argument("--case-id")
    policy_reference.add_argument("--disruption-id")

    search = commands.add_parser("search-alternative-itineraries")
    search.add_argument("origin")
    search.add_argument("destination")
    search.add_argument("earliest_departure")
    search.add_argument("latest_arrival")
    search.add_argument("passenger_count", type=int)
    search.add_argument("--max-connections", type=int, choices=(0, 1), default=1)

    validation = commands.add_parser("validate-itinerary")
    validation.add_argument("candidate_id")
    validation.add_argument("passenger_count", type=int)
    validation.add_argument("flight_ids", nargs="+")
    return parser


def build_runtime() -> tuple[ToolRuntime, Disposable]:
    """Wire adapters to application services and PostgreSQL at the outer edge."""

    engine = create_database_engine(Settings())
    session_factory = create_session_factory(engine)
    unit_of_work_factory = partial(SqlAlchemyRecoveryDataUnitOfWork, session_factory)
    service = OperationalQueryService(unit_of_work_factory)
    return (
        ToolRuntime(
            get_booking=GetBookingTool(service),
            get_flight_status=GetFlightStatusTool(service),
            get_disruption_policy=GetDisruptionPolicyTool(service),
            search_alternative_itineraries=SearchAlternativeItinerariesTool(service),
            validate_itinerary=ValidateItineraryTool(service),
        ),
        engine,
    )


def _context(
    parsed: argparse.Namespace, permission: ToolPermission
) -> ToolExecutionContext:
    """Create a least-privilege execution context with an absolute deadline."""

    timeout_seconds = cast(int, parsed.timeout_seconds)
    if timeout_seconds <= 0:
        raise ValueError("timeout-seconds must be positive")
    return ToolExecutionContext(
        actor_id=cast(str, parsed.actor_id),
        correlation_id=cast(str, parsed.correlation_id),
        permissions=frozenset({permission}),
        deadline_at=datetime.now(UTC) + timedelta(seconds=timeout_seconds),
    )


def _invoke(parsed: argparse.Namespace, runtime: ToolRuntime) -> BaseModel:
    """Route parsed manual input through exactly one guarded tool adapter."""

    command = cast(str, parsed.command)
    result: BaseModel
    if command == "get-booking":
        result = runtime.get_booking.invoke(
            {"booking_id": parsed.booking_id},
            _context(parsed, ToolPermission.READ_BOOKING),
        )
    elif command == "get-flight-status":
        result = runtime.get_flight_status.invoke(
            {"flight_id": parsed.flight_id},
            _context(parsed, ToolPermission.READ_FLIGHT_STATUS),
        )
    elif command == "get-disruption-policy":
        if parsed.case_id is not None:
            reference = {"type": "recovery_case", "id": parsed.case_id}
        else:
            reference = {"type": "disruption", "id": parsed.disruption_id}
        result = runtime.get_disruption_policy.invoke(
            {"reference": reference},
            _context(parsed, ToolPermission.READ_DISRUPTION_POLICY),
        )
    elif command == "search-alternative-itineraries":
        result = runtime.search_alternative_itineraries.invoke(
            {
                "origin": parsed.origin,
                "destination": parsed.destination,
                "earliest_departure": parsed.earliest_departure,
                "latest_arrival": parsed.latest_arrival,
                "passenger_count": parsed.passenger_count,
                "max_connections": parsed.max_connections,
            },
            _context(parsed, ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES),
        )
    else:
        result = runtime.validate_itinerary.invoke(
            {
                "candidate": {
                    "candidate_id": parsed.candidate_id,
                    "flight_ids": parsed.flight_ids,
                    "passenger_count": parsed.passenger_count,
                }
            },
            _context(parsed, ToolPermission.VALIDATE_ITINERARY),
        )
    return result


def main(
    arguments: Sequence[str] | None = None,
    *,
    runtime: ToolRuntime | None = None,
) -> int:
    """Print one structured result and return a shell-friendly exit code."""

    parser = build_parser()
    parsed = parser.parse_args(arguments)
    if parsed.command == "catalog":
        print(
            "[\n"
            + ",\n".join(schema.model_dump_json(indent=2) for schema in TOOL_SCHEMAS)
            + "\n]"
        )
        return 0

    owned_resource: Disposable | None = None
    try:
        if runtime is None:
            runtime, owned_resource = build_runtime()
        result = _invoke(parsed, runtime)
        print(result.model_dump_json(indent=2))
        return 0 if isinstance(result, ToolSuccess) else 1
    except (DatabaseConfigurationError, ValidationError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if owned_resource is not None:
            owned_resource.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
