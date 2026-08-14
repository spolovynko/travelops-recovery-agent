"""Context trace integration tests."""

from datetime import UTC, datetime

from travelops_recovery_agent.context_engineering.inspector import (
    ContextInspectorService,
)
from travelops_recovery_agent.context_engineering.models import ContextTask
from travelops_recovery_agent.context_engineering.observability import (
    context_trace_events,
)


def test_context_trace_uses_existing_schema_and_safe_aggregate_fields() -> None:
    result = ContextInspectorService().inspect(
        case_id="CASE-0002",
        task=ContextTask.INVESTIGATE,
        workflow_node="model_reasoning",
        operator_role="recovery_operator",
        now=datetime(2026, 8, 14, 12, tzinfo=UTC),
    )

    events = context_trace_events(
        result,
        trace_id="trace-1",
        request_id="request-1",
        workflow_run_id="run-1",
    )

    assert [event.status for event in events] == ["started", "succeeded"]
    assert events[1].metadata["selected_count"] == len(result.selected)
    serialized = events[1].model_dump_json().lower()
    assert "credential" not in serialized
    assert "authorization headers" not in serialized
