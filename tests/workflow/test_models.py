"""Workflow identity, lifecycle, and safe-event contract tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.workflow.models import (
    WorkflowEvent,
    WorkflowEventType,
    WorkflowStatus,
    new_workflow_identity,
)


def test_case_run_and_thread_identifiers_are_stable_and_distinct() -> None:
    first = new_workflow_identity("CASE-0007")
    second = new_workflow_identity("CASE-0007")

    assert first.case_id == second.case_id == "CASE-0007"
    assert first.run_id != second.run_id
    assert first.thread_id != second.thread_id
    assert first.run_id != first.thread_id


def test_workflow_status_partitions_active_and_terminal_values() -> None:
    assert WorkflowStatus.RUNNING.is_active
    assert WorkflowStatus.PAUSED.is_active
    assert not WorkflowStatus.COMPLETED.is_active
    assert WorkflowStatus.COMPLETED.is_terminal
    assert WorkflowStatus.CANCELLED.is_terminal


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "hidden"},
        {"nested": {"sql": "select *"}},
        {"items": [{"arguments": {"booking_id": "BKG-0007"}}]},
        {"exception": "internal stack"},
        {"passengers": ["Synthetic Person"]},
    ],
)
def test_safe_event_payload_rejects_sensitive_fields(payload: object) -> None:
    with pytest.raises(ValidationError, match="unsafe workflow event field"):
        WorkflowEvent.create(
            run_id="run-test",
            sequence=1,
            type=WorkflowEventType.NODE_COMPLETED,
            occurred_at=datetime.now(UTC),
            payload=payload,  # type: ignore[arg-type]
        )


def test_safe_event_accepts_bounded_operator_projection() -> None:
    event = WorkflowEvent.create(
        run_id="run-test",
        sequence=2,
        type=WorkflowEventType.TOOL_COMPLETED,
        occurred_at=datetime.now(UTC),
        payload={
            "tool_name": "get_flight_status",
            "ok": True,
            "observation_id": "observation-1",
        },
    )

    assert event.event_id == "run-test:2"
    assert event.payload["ok"] is True
