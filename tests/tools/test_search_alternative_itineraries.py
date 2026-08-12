"""Boundary tests for deterministic alternative-itinerary search."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from travelops_recovery_agent.application.query_models import (
    AlternativeItinerary,
    AlternativeSearchRequirements,
)
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.tools.adapters import SearchAlternativeItinerariesTool
from travelops_recovery_agent.tools.contracts import (
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import SearchAlternativeItinerariesOutput

NOW = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


class SearchServiceStub:
    def __init__(self, result: tuple[AlternativeItinerary, ...]) -> None:
        self.result = result
        self.requirements: list[AlternativeSearchRequirements] = []
        self.error: Exception | None = None

    def search_alternative_itineraries(
        self,
        requirements: AlternativeSearchRequirements,
    ) -> tuple[AlternativeItinerary, ...]:
        self.requirements.append(requirements)
        if self.error is not None:
            raise self.error
        return self.result


def candidate() -> AlternativeItinerary:
    flights = generate_dataset(seed=42).flights[:2]
    return AlternativeItinerary(flights=flights, connection_minutes=(90,))


def input_data() -> dict[str, object]:
    return {
        "origin": "ZRA",
        "destination": "XLC",
        "earliest_departure": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        "latest_arrival": datetime(2026, 1, 15, 18, 0, tzinfo=UTC),
        "passenger_count": 3,
        "max_connections": 1,
    }


def context(
    *,
    permissions: frozenset[ToolPermission] | None = None,
    deadline_at: datetime | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        actor_id="operator-17",
        correlation_id="request-search-1",
        permissions=(
            permissions
            if permissions is not None
            else frozenset({ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES})
        ),
        deadline_at=deadline_at or NOW + timedelta(minutes=5),
    )


def build_tool(
    stub: SearchServiceStub,
    clock: Callable[[], datetime] = lambda: NOW,
) -> SearchAlternativeItinerariesTool:
    return SearchAlternativeItinerariesTool(
        cast(OperationalQueryService, stub),
        clock=clock,
    )


def require_success(
    result: ToolSuccess[SearchAlternativeItinerariesOutput] | ToolFailure,
) -> ToolSuccess[SearchAlternativeItinerariesOutput]:
    assert isinstance(result, ToolSuccess)
    return result


def require_failure(
    result: ToolSuccess[SearchAlternativeItinerariesOutput] | ToolFailure,
) -> ToolFailure:
    assert isinstance(result, ToolFailure)
    return result


def test_search_returns_deterministic_candidates_and_explicit_deferrals() -> None:
    stub = SearchServiceStub((candidate(),))

    result = require_success(build_tool(stub).invoke(input_data(), context()))

    assert result.result.candidates[0].candidate_id == ("CAND-FLT-NV101-FLT-NV102")
    assert result.result.candidates[0].connection_minutes == (90,)
    assert result.result.passenger_count == 3
    assert result.result.inventory_status == "not_evaluated"
    assert result.result.deferred_validations == ("seat_inventory", "ticket_rules")
    assert result.audit.required_permission is (
        ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES
    )


@pytest.mark.parametrize(
    ("payload_change", "tool_context", "expected_code"),
    [
        ({"origin": "BA"}, context(), ToolErrorCode.INVALID_INPUT),
        ({}, context(permissions=frozenset()), ToolErrorCode.PERMISSION_DENIED),
        (
            {},
            context(deadline_at=NOW - timedelta(seconds=1)),
            ToolErrorCode.DEADLINE_EXCEEDED,
        ),
    ],
)
def test_search_rejects_before_service_access(
    payload_change: dict[str, object],
    tool_context: ToolExecutionContext,
    expected_code: ToolErrorCode,
) -> None:
    stub = SearchServiceStub((candidate(),))
    payload = input_data() | payload_change

    result = require_failure(build_tool(stub).invoke(payload, tool_context))

    assert result.error.code is expected_code
    assert stub.requirements == []


def test_search_returns_an_empty_success_instead_of_not_found() -> None:
    result = require_success(
        build_tool(SearchServiceStub(())).invoke(input_data(), context())
    )

    assert result.result.candidates == ()


def test_search_hides_dependency_failures() -> None:
    stub = SearchServiceStub(())
    stub.error = RuntimeError("database password unsafe-secret")

    result = require_failure(build_tool(stub).invoke(input_data(), context()))

    assert result.error.code is ToolErrorCode.DEPENDENCY_FAILURE
    assert "unsafe-secret" not in result.model_dump_json()


def test_search_is_deterministic_for_the_same_state_input_and_clock() -> None:
    tool = build_tool(SearchServiceStub((candidate(),)))

    assert tool.invoke(input_data(), context()) == tool.invoke(input_data(), context())
