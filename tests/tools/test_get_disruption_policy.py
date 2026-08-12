"""Boundary tests for the get_disruption_policy operational tool."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from travelops_recovery_agent.application.query_models import ResolvedDisruptionPolicy
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import DisruptionId, RecoveryCaseId
from travelops_recovery_agent.tools.adapters import GetDisruptionPolicyTool
from travelops_recovery_agent.tools.contracts import (
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import GetDisruptionPolicyOutput

NOW = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


def policy_resolution() -> ResolvedDisruptionPolicy:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[0]
    disruption = dataset.disruptions[0]
    return ResolvedDisruptionPolicy(
        recovery_case=recovery_case,
        disruption=disruption,
        policy=dataset.policies[0],
    )


class PolicyServiceStub:
    def __init__(self, result: ResolvedDisruptionPolicy | None) -> None:
        self.result = result
        self.case_ids: list[RecoveryCaseId] = []
        self.disruption_ids: list[DisruptionId] = []
        self.error: Exception | None = None

    def get_disruption_policy_for_case(
        self,
        case_id: RecoveryCaseId,
    ) -> ResolvedDisruptionPolicy | None:
        self.case_ids.append(case_id)
        if self.error is not None:
            raise self.error
        return self.result

    def get_disruption_policy_for_disruption(
        self,
        disruption_id: DisruptionId,
    ) -> ResolvedDisruptionPolicy | None:
        self.disruption_ids.append(disruption_id)
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
        correlation_id="request-policy-1",
        permissions=(
            permissions
            if permissions is not None
            else frozenset({ToolPermission.READ_DISRUPTION_POLICY})
        ),
        deadline_at=deadline_at or NOW + timedelta(minutes=5),
    )


def build_tool(
    stub: PolicyServiceStub,
    clock: Callable[[], datetime] = lambda: NOW,
) -> GetDisruptionPolicyTool:
    return GetDisruptionPolicyTool(cast(OperationalQueryService, stub), clock=clock)


def require_success(
    result: ToolSuccess[GetDisruptionPolicyOutput] | ToolFailure,
) -> ToolSuccess[GetDisruptionPolicyOutput]:
    assert isinstance(result, ToolSuccess)
    return result


def require_failure(
    result: ToolSuccess[GetDisruptionPolicyOutput] | ToolFailure,
) -> ToolFailure:
    assert isinstance(result, ToolFailure)
    return result


@pytest.mark.parametrize(
    ("reference", "expected_via"),
    [
        ({"type": "recovery_case", "id": "CASE-0001"}, "recovery_case"),
        ({"type": "disruption", "id": "DIS-0001"}, "disruption"),
    ],
)
def test_get_disruption_policy_returns_structured_policy_facts(
    reference: dict[str, str],
    expected_via: str,
) -> None:
    stub = PolicyServiceStub(policy_resolution())

    result = require_success(
        build_tool(stub).invoke({"reference": reference}, context())
    )

    assert result.result.resolved_via == expected_via
    assert result.result.policy_id == "POL-STANDARD"
    assert result.result.disruption_type.value == "delayed_flight"
    assert result.result.rebooking_window_hours == 24
    assert result.audit.required_permission is ToolPermission.READ_DISRUPTION_POLICY


@pytest.mark.parametrize(
    ("input_data", "tool_context", "expected_code"),
    [
        (
            {"reference": {"type": "bad", "id": "DIS-0001"}},
            context(),
            ToolErrorCode.INVALID_INPUT,
        ),
        (
            {"reference": {"type": "disruption", "id": "DIS-0001"}},
            context(permissions=frozenset()),
            ToolErrorCode.PERMISSION_DENIED,
        ),
        (
            {"reference": {"type": "disruption", "id": "DIS-0001"}},
            context(deadline_at=NOW - timedelta(seconds=1)),
            ToolErrorCode.DEADLINE_EXCEEDED,
        ),
    ],
)
def test_get_disruption_policy_rejects_before_service_access(
    input_data: object,
    tool_context: ToolExecutionContext,
    expected_code: ToolErrorCode,
) -> None:
    stub = PolicyServiceStub(policy_resolution())

    result = require_failure(build_tool(stub).invoke(input_data, tool_context))

    assert result.error.code is expected_code
    assert stub.case_ids == []
    assert stub.disruption_ids == []


def test_get_disruption_policy_returns_typed_not_found() -> None:
    result = require_failure(
        build_tool(PolicyServiceStub(None)).invoke(
            {"reference": {"type": "disruption", "id": "DIS-9999"}},
            context(),
        )
    )

    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert result.error.retryable is False


def test_get_disruption_policy_hides_dependency_details() -> None:
    stub = PolicyServiceStub(None)
    stub.error = RuntimeError("database password unsafe-secret")

    result = require_failure(
        build_tool(stub).invoke(
            {"reference": {"type": "disruption", "id": "DIS-0001"}},
            context(),
        )
    )

    assert result.error.code is ToolErrorCode.DEPENDENCY_FAILURE
    assert "unsafe-secret" not in result.model_dump_json()
