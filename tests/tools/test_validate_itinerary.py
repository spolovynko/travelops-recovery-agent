"""Boundary tests for deterministic itinerary validation."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from travelops_recovery_agent.application.query_models import ItineraryValidationResult
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRule,
    ItineraryRuleResult,
    RuleStatus,
)
from travelops_recovery_agent.domain.models import FlightId
from travelops_recovery_agent.tools.adapters import ValidateItineraryTool
from travelops_recovery_agent.tools.contracts import (
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import ValidateItineraryOutput

NOW = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


def validation(*, valid: bool = True) -> ItineraryValidationResult:
    return ItineraryValidationResult(
        flight_ids=("FLT-NV101", "FLT-NV102"),
        valid=valid,
        rules=(
            ItineraryRuleResult(
                rule=ItineraryRule.FLIGHTS_EXIST,
                status=RuleStatus.PASSED,
                reason="every requested flight exists in stored business data",
            ),
            ItineraryRuleResult(
                rule=ItineraryRule.ROUTE_CONTINUITY,
                status=RuleStatus.PASSED if valid else RuleStatus.FAILED,
                reason="route result",
            ),
            ItineraryRuleResult(
                rule=ItineraryRule.CHRONOLOGICAL_ORDER,
                status=RuleStatus.PASSED,
                reason="time result",
            ),
        ),
    )


class ValidationServiceStub:
    def __init__(self, result: ItineraryValidationResult) -> None:
        self.result = result
        self.flight_ids: list[tuple[FlightId, ...]] = []
        self.error: Exception | None = None

    def validate_itinerary(
        self,
        flight_ids: tuple[FlightId, ...],
    ) -> ItineraryValidationResult:
        self.flight_ids.append(flight_ids)
        if self.error is not None:
            raise self.error
        return self.result


def input_data() -> dict[str, object]:
    return {
        "candidate": {
            "candidate_id": "CAND-FLT-NV101-FLT-NV102",
            "flight_ids": ["FLT-NV101", "FLT-NV102"],
            "passenger_count": 2,
        }
    }


def context(
    *,
    permissions: frozenset[ToolPermission] | None = None,
    deadline_at: datetime | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        actor_id="operator-17",
        correlation_id="request-validation-1",
        permissions=(
            permissions
            if permissions is not None
            else frozenset({ToolPermission.VALIDATE_ITINERARY})
        ),
        deadline_at=deadline_at or NOW + timedelta(minutes=5),
    )


def build_tool(
    stub: ValidationServiceStub,
    clock: Callable[[], datetime] = lambda: NOW,
) -> ValidateItineraryTool:
    return ValidateItineraryTool(cast(OperationalQueryService, stub), clock=clock)


def require_success(
    result: ToolSuccess[ValidateItineraryOutput] | ToolFailure,
) -> ToolSuccess[ValidateItineraryOutput]:
    assert isinstance(result, ToolSuccess)
    return result


def require_failure(
    result: ToolSuccess[ValidateItineraryOutput] | ToolFailure,
) -> ToolFailure:
    assert isinstance(result, ToolFailure)
    return result


def test_validate_itinerary_returns_fixed_rule_results_and_deferrals() -> None:
    result = require_success(
        build_tool(ValidationServiceStub(validation())).invoke(input_data(), context())
    )

    assert result.result.valid is True
    assert [rule.rule.value for rule in result.result.rules] == [
        "flights_exist",
        "route_continuity",
        "chronological_order",
    ]
    assert result.result.deferred_validations == (
        "minimum_connection_policy",
        "seat_inventory",
        "ticket_rules",
    )


def test_caller_cannot_declare_the_candidate_valid() -> None:
    stub = ValidationServiceStub(validation())
    payload = input_data()
    candidate = cast(dict[str, object], payload["candidate"])
    candidate["valid"] = True

    result = require_failure(build_tool(stub).invoke(payload, context()))

    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert stub.flight_ids == []


@pytest.mark.parametrize(
    ("tool_context", "expected_code"),
    [
        (context(permissions=frozenset()), ToolErrorCode.PERMISSION_DENIED),
        (
            context(deadline_at=NOW - timedelta(seconds=1)),
            ToolErrorCode.DEADLINE_EXCEEDED,
        ),
    ],
)
def test_validate_itinerary_rejects_before_service_access(
    tool_context: ToolExecutionContext,
    expected_code: ToolErrorCode,
) -> None:
    stub = ValidationServiceStub(validation())

    result = require_failure(build_tool(stub).invoke(input_data(), tool_context))

    assert result.error.code is expected_code
    assert stub.flight_ids == []


def test_validate_itinerary_returns_not_found_for_unknown_stored_flights() -> None:
    missing = ItineraryValidationResult(
        flight_ids=("FLT-MISSING",),
        valid=False,
        rules=(
            ItineraryRuleResult(
                rule=ItineraryRule.FLIGHTS_EXIST,
                status=RuleStatus.FAILED,
                reason="missing stored flights: FLT-MISSING",
            ),
        ),
    )
    payload = {
        "candidate": {
            "candidate_id": "CAND-MISSING",
            "flight_ids": ["FLT-MISSING"],
            "passenger_count": 1,
        }
    }

    result = require_failure(
        build_tool(ValidationServiceStub(missing)).invoke(payload, context())
    )

    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert result.error.retryable is False


def test_validate_itinerary_hides_dependency_failures() -> None:
    stub = ValidationServiceStub(validation())
    stub.error = RuntimeError("database password unsafe-secret")

    result = require_failure(build_tool(stub).invoke(input_data(), context()))

    assert result.error.code is ToolErrorCode.DEPENDENCY_FAILURE
    assert "unsafe-secret" not in result.model_dump_json()


def test_validate_itinerary_is_deterministic() -> None:
    tool = build_tool(ValidationServiceStub(validation(valid=False)))

    assert tool.invoke(input_data(), context()) == tool.invoke(input_data(), context())
