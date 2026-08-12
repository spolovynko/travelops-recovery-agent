"""Boundary tests for the get_booking operational tool."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from travelops_recovery_agent.application.query_models import CompleteBooking
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import BookingId
from travelops_recovery_agent.tools.adapters import GetBookingTool
from travelops_recovery_agent.tools.contracts import (
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import GetBookingOutput

NOW = datetime(2026, 1, 15, 11, 0, tzinfo=UTC)


def complete_booking(case_index: int = 6) -> CompleteBooking:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    booking = next(
        item for item in dataset.bookings if item.id == recovery_case.booking_id
    )
    passengers_by_id = {passenger.id: passenger for passenger in dataset.passengers}
    flights_by_id = {flight.id: flight for flight in dataset.flights}
    return CompleteBooking(
        booking=booking,
        passengers=tuple(
            passengers_by_id[passenger_id] for passenger_id in booking.passenger_ids
        ),
        flights=tuple(flights_by_id[segment.flight_id] for segment in booking.segments),
    )


class QueryServiceStub:
    def __init__(self, result: CompleteBooking | None) -> None:
        self.result = result
        self.requested_booking_ids: list[BookingId] = []
        self.error: Exception | None = None

    def get_booking(self, booking_id: BookingId) -> CompleteBooking | None:
        self.requested_booking_ids.append(booking_id)
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
        correlation_id="request-4f6a",
        permissions=(
            permissions
            if permissions is not None
            else frozenset({ToolPermission.READ_BOOKING})
        ),
        deadline_at=deadline_at or NOW + timedelta(minutes=5),
    )


def build_tool(
    stub: QueryServiceStub,
    clock: Callable[[], datetime] = lambda: NOW,
) -> GetBookingTool:
    return GetBookingTool(
        cast(OperationalQueryService, stub),
        clock=clock,
    )


def require_success(
    result: ToolSuccess[GetBookingOutput] | ToolFailure,
) -> ToolSuccess[GetBookingOutput]:
    assert isinstance(result, ToolSuccess)
    return result


def require_failure(
    result: ToolSuccess[GetBookingOutput] | ToolFailure,
) -> ToolFailure:
    assert isinstance(result, ToolFailure)
    return result


def test_get_booking_returns_a_minimized_coherent_booking_view() -> None:
    stub = QueryServiceStub(complete_booking())
    result = require_success(
        build_tool(stub).invoke(
            {"booking_id": "BKG-0007"},
            context(),
        )
    )

    assert result.result.booking_id == "BKG-0007"
    assert [passenger.passenger_id for passenger in result.result.passengers] == [
        "PAX-0007",
        "PAX-0008",
        "PAX-0009",
    ]
    assert [segment.sequence for segment in result.result.itinerary] == [1, 2]
    assert [segment.flight_id for segment in result.result.itinerary] == [
        "FLT-NV113",
        "FLT-NV114",
    ]
    assert stub.requested_booking_ids == ["BKG-0007"]
    assert result.audit.tool_name == "get_booking"
    assert result.audit.actor_id == "operator-17"
    assert result.audit.required_permission is ToolPermission.READ_BOOKING
    assert result.audit.outcome.value == "succeeded"


def test_get_booking_rejects_invalid_input_before_service_access() -> None:
    stub = QueryServiceStub(complete_booking())
    result = require_failure(
        build_tool(stub).invoke(
            {"booking_id": "not-a-booking"},
            context(),
        )
    )

    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert result.error.retryable is False
    assert stub.requested_booking_ids == []
    assert result.audit.outcome.value == "rejected"


def test_get_booking_rejects_missing_permission_before_service_access() -> None:
    stub = QueryServiceStub(complete_booking())
    result = require_failure(
        build_tool(stub).invoke(
            {"booking_id": "BKG-0007"},
            context(permissions=frozenset()),
        )
    )

    assert result.error.code is ToolErrorCode.PERMISSION_DENIED
    assert stub.requested_booking_ids == []
    assert result.audit.outcome.value == "rejected"


def test_get_booking_rejects_expired_deadline_before_service_access() -> None:
    stub = QueryServiceStub(complete_booking())
    result = require_failure(
        build_tool(stub).invoke(
            {"booking_id": "BKG-0007"},
            context(deadline_at=NOW - timedelta(seconds=1)),
        )
    )

    assert result.error.code is ToolErrorCode.DEADLINE_EXCEEDED
    assert stub.requested_booking_ids == []
    assert result.audit.outcome.value == "rejected"


def test_get_booking_rejects_a_deadline_exceeded_during_service_access() -> None:
    stub = QueryServiceStub(complete_booking())
    clock_values = iter(
        (
            NOW,
            NOW + timedelta(minutes=6),
            NOW + timedelta(minutes=6),
        )
    )
    result = require_failure(
        build_tool(stub, clock=lambda: next(clock_values)).invoke(
            {"booking_id": "BKG-0007"},
            context(deadline_at=NOW + timedelta(minutes=5)),
        )
    )

    assert result.error.code is ToolErrorCode.DEADLINE_EXCEEDED
    assert result.error.retryable is False
    assert stub.requested_booking_ids == ["BKG-0007"]
    assert result.audit.outcome.value == "failed"


def test_get_booking_returns_a_typed_not_found_error() -> None:
    stub = QueryServiceStub(None)
    result = require_failure(
        build_tool(stub).invoke(
            {"booking_id": "BKG-9999"},
            context(),
        )
    )

    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert result.error.retryable is False
    assert "BKG-9999" in result.error.message
    assert result.audit.outcome.value == "rejected"


def test_get_booking_hides_internal_dependency_failures() -> None:
    stub = QueryServiceStub(None)
    stub.error = RuntimeError(
        "postgresql://operator:unsafe-password@database.invalid/travelops"
    )
    result = require_failure(
        build_tool(stub).invoke(
            {"booking_id": "BKG-0007"},
            context(),
        )
    )

    serialized = result.model_dump_json()
    assert result.error.code is ToolErrorCode.DEPENDENCY_FAILURE
    assert result.error.retryable is True
    assert result.audit.outcome.value == "failed"
    assert "unsafe-password" not in serialized
    assert "database.invalid" not in serialized
    assert "traceback" not in serialized.lower()


def test_get_booking_is_deterministic_with_the_same_state_input_and_clock() -> None:
    stub = QueryServiceStub(complete_booking())
    tool = build_tool(stub)

    first = tool.invoke({"booking_id": "BKG-0007"}, context())
    second = tool.invoke({"booking_id": "BKG-0007"}, context())

    assert first == second
