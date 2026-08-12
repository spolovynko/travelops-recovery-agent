"""Contract tests for the shared operational-tool boundary."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from travelops_recovery_agent.tools.contracts import (
    ToolAuditMetadata,
    ToolAuditOutcome,
    ToolError,
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


def valid_context_data() -> dict[str, object]:
    return {
        "actor_id": "operator-17",
        "correlation_id": "request-4f6a",
        "permissions": ["booking:read", "flight_status:read"],
        "deadline_at": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
    }


def valid_audit_data() -> dict[str, object]:
    started_at = datetime(2026, 1, 15, 11, 59, tzinfo=UTC)
    return {
        "tool_name": "get_booking",
        "actor_id": "operator-17",
        "correlation_id": "request-4f6a",
        "required_permission": "booking:read",
        "outcome": "succeeded",
        "started_at": started_at,
        "completed_at": started_at + timedelta(milliseconds=8),
        "duration_ms": 8,
    }


def test_permission_vocabulary_is_narrow_and_stable() -> None:
    assert {permission.value for permission in ToolPermission} == {
        "booking:read",
        "flight_status:read",
        "disruption_policy:read",
        "alternative_itineraries:search",
        "itinerary:validate",
    }


def test_error_taxonomy_is_small_and_stable() -> None:
    assert {code.value for code in ToolErrorCode} == {
        "invalid_input",
        "not_found",
        "permission_denied",
        "deadline_exceeded",
        "dependency_failure",
    }


def test_execution_context_accepts_only_justified_metadata() -> None:
    context = ToolExecutionContext.model_validate(valid_context_data())

    assert context.actor_id == "operator-17"
    assert context.correlation_id == "request-4f6a"
    assert context.permissions == frozenset(
        {ToolPermission.READ_BOOKING, ToolPermission.READ_FLIGHT_STATUS}
    )
    assert context.deadline_at.tzinfo is UTC

    schema = ToolExecutionContext.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "actor_id",
        "correlation_id",
        "permissions",
        "deadline_at",
    }


@pytest.mark.parametrize("field", ["actor_id", "correlation_id"])
def test_execution_context_rejects_blank_identity_metadata(field: str) -> None:
    context_data = valid_context_data()
    context_data[field] = "   "

    with pytest.raises(ValidationError, match=field):
        ToolExecutionContext.model_validate(context_data)


def test_execution_context_requires_a_timezone_aware_deadline() -> None:
    context_data = valid_context_data()
    context_data["deadline_at"] = datetime(2026, 1, 15, 12, 0)

    with pytest.raises(ValidationError, match="deadline_at must be timezone-aware"):
        ToolExecutionContext.model_validate(context_data)


def test_execution_context_rejects_credentials_and_unplanned_metadata() -> None:
    context_data = valid_context_data()
    context_data["database_url"] = "postgresql://secret@example.invalid/travelops"

    with pytest.raises(ValidationError, match="database_url"):
        ToolExecutionContext.model_validate(context_data)


def test_audit_metadata_contains_only_safe_operational_facts() -> None:
    audit = ToolAuditMetadata.model_validate(valid_audit_data())

    assert audit.outcome is ToolAuditOutcome.SUCCEEDED
    assert audit.required_permission is ToolPermission.READ_BOOKING

    payload = audit.model_dump(mode="json")
    assert set(payload) == {
        "tool_name",
        "actor_id",
        "correlation_id",
        "required_permission",
        "outcome",
        "started_at",
        "completed_at",
        "duration_ms",
    }
    serialized = audit.model_dump_json()
    assert "password" not in serialized.lower()
    assert "database" not in serialized.lower()
    assert "passenger" not in serialized.lower()


def test_audit_metadata_rejects_invalid_timing() -> None:
    audit_data = valid_audit_data()
    audit_data["completed_at"] = datetime(2026, 1, 15, 11, 58, tzinfo=UTC)

    with pytest.raises(ValidationError, match="completed_at must not precede"):
        ToolAuditMetadata.model_validate(audit_data)


def test_success_result_is_typed_and_serializable() -> None:
    result = ToolSuccess[ExampleOutput](
        result=ExampleOutput(value="safe structured value"),
        audit=ToolAuditMetadata.model_validate(valid_audit_data()),
    )

    assert result.ok is True
    assert result.result.value == "safe structured value"
    assert result.model_dump(mode="json")["result"] == {
        "value": "safe structured value"
    }


def test_failure_result_uses_a_safe_typed_error() -> None:
    audit_data = valid_audit_data()
    audit_data["outcome"] = "rejected"
    result = ToolFailure(
        error=ToolError(
            code=ToolErrorCode.PERMISSION_DENIED,
            message="permission denied",
            retryable=False,
        ),
        audit=ToolAuditMetadata.model_validate(audit_data),
    )

    assert result.ok is False
    assert result.error.code is ToolErrorCode.PERMISSION_DENIED
    assert result.error.retryable is False
    assert "traceback" not in result.model_dump_json().lower()


def test_all_contract_models_reject_unknown_fields() -> None:
    error_payload = {
        "code": "dependency_failure",
        "message": "operational dependency failed",
        "retryable": True,
        "internal_exception": "password=unsafe",
    }

    with pytest.raises(ValidationError, match="internal_exception"):
        ToolError.model_validate(error_payload)
