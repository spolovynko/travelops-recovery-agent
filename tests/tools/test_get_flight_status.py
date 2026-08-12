"""Boundary tests for the get_flight_status operational tool."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from travelops_recovery_agent.application.query_models import (
    FlightStatus,
    OperationalFlightStatus,
)
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import FlightId
from travelops_recovery_agent.tools.adapters import GetFlightStatusTool
from travelops_recovery_agent.tools.contracts import (
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import (
    FlightOperationalStatus,
    GetFlightStatusOutput,
)

NOW = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


def delayed_status() -> FlightStatus:
    dataset = generate_dataset(seed=42)
    disruption = dataset.disruptions[0]
    flight = next(
        item for item in dataset.flights if item.id == disruption.affected_flight_id
    )
    return FlightStatus(
        flight=flight,
        status=OperationalFlightStatus.DELAYED,
        delay_minutes=30,
        cancellation_reason=None,
        related_disruptions=(disruption,),
    )


class FlightStatusServiceStub:
    def __init__(self, result: FlightStatus | None) -> None:
        self.result = result
        self.requested_flight_ids: list[FlightId] = []
        self.error: Exception | None = None

    def get_flight_status(self, flight_id: FlightId) -> FlightStatus | None:
        self.requested_flight_ids.append(flight_id)
        if self.error is not None:
            raise self.error
        return self.result


def context(
    *,
    permissions: frozenset[ToolPermission] | None = None,
    deadline_at: datetime | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        actor_id="operator-17",
        correlation_id="request-flight-1",
        permissions=(
            permissions
            if permissions is not None
            else frozenset({ToolPermission.READ_FLIGHT_STATUS})
        ),
        deadline_at=deadline_at or NOW + timedelta(minutes=5),
    )


def build_tool(
    stub: FlightStatusServiceStub,
    clock: Callable[[], datetime] = lambda: NOW,
) -> GetFlightStatusTool:
    return GetFlightStatusTool(cast(OperationalQueryService, stub), clock=clock)


def require_success(
    result: ToolSuccess[GetFlightStatusOutput] | ToolFailure,
) -> ToolSuccess[GetFlightStatusOutput]:
    assert isinstance(result, ToolSuccess)
    return result


def require_failure(
    result: ToolSuccess[GetFlightStatusOutput] | ToolFailure,
) -> ToolFailure:
    assert isinstance(result, ToolFailure)
    return result


def test_get_flight_status_returns_scheduled_facts_and_synthetic_status() -> None:
    stub = FlightStatusServiceStub(delayed_status())

    result = require_success(
        build_tool(stub).invoke({"flight_id": "FLT-NV101"}, context())
    )

    assert result.result.flight_id == "FLT-NV101"
    assert result.result.operational_status is FlightOperationalStatus.DELAYED
    assert result.result.delay_minutes == 30
    assert result.result.source == "synthetic_dataset"
    assert result.result.related_disruptions[0].disruption_id == "DIS-0001"
    assert result.audit.required_permission is ToolPermission.READ_FLIGHT_STATUS
    assert stub.requested_flight_ids == ["FLT-NV101"]


@pytest.mark.parametrize(
    ("input_data", "tool_context", "expected_code"),
    [
        (
            {"flight_id": "bad-id"},
            context(),
            ToolErrorCode.INVALID_INPUT,
        ),
        (
            {"flight_id": "FLT-NV101"},
            context(permissions=frozenset()),
            ToolErrorCode.PERMISSION_DENIED,
        ),
        (
            {"flight_id": "FLT-NV101"},
            context(deadline_at=NOW - timedelta(seconds=1)),
            ToolErrorCode.DEADLINE_EXCEEDED,
        ),
    ],
)
def test_get_flight_status_rejects_before_service_access(
    input_data: object,
    tool_context: ToolExecutionContext,
    expected_code: ToolErrorCode,
) -> None:
    stub = FlightStatusServiceStub(delayed_status())

    result = require_failure(build_tool(stub).invoke(input_data, tool_context))

    assert result.error.code is expected_code
    assert result.error.retryable is False
    assert result.audit.outcome.value == "rejected"
    assert stub.requested_flight_ids == []


def test_get_flight_status_returns_typed_not_found() -> None:
    stub = FlightStatusServiceStub(None)

    result = require_failure(
        build_tool(stub).invoke({"flight_id": "FLT-NV999"}, context())
    )

    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert result.error.retryable is False
    assert "FLT-NV999" in result.error.message


def test_get_flight_status_hides_dependency_details() -> None:
    stub = FlightStatusServiceStub(None)
    stub.error = RuntimeError("database password unsafe-secret")

    result = require_failure(
        build_tool(stub).invoke({"flight_id": "FLT-NV101"}, context())
    )

    serialized = result.model_dump_json()
    assert result.error.code is ToolErrorCode.DEPENDENCY_FAILURE
    assert result.error.retryable is True
    assert "unsafe-secret" not in serialized


def test_get_flight_status_is_deterministic() -> None:
    tool = build_tool(FlightStatusServiceStub(delayed_status()))

    first = tool.invoke({"flight_id": "FLT-NV101"}, context())
    second = tool.invoke({"flight_id": "FLT-NV101"}, context())

    assert first == second
