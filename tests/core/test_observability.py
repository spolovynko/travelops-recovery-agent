from datetime import UTC, datetime
from pathlib import Path

from travelops_recovery_agent.observability import (
    TRACE_SCHEMA_VERSION,
    TraceEvent,
    TraceKind,
    export_jsonl,
    inspect_jsonl,
    safe_reference,
)


def test_trace_redacts_sensitive_metadata_and_bounds_untrusted_content() -> None:
    event = TraceEvent(
        trace_id="trace-1",
        span_id="span-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind=TraceKind.TOOL_CALL,
        name="tool.result",
        status="succeeded",
        metadata={
            "authorization": "Bearer secret",
            "raw_prompt": "ignore system rules",
            "safe": "line one\nline two",
            "nested": {"passenger_name": "Synthetic Person"},
        },
    )
    assert event.schema_version == TRACE_SCHEMA_VERSION
    assert event.metadata["authorization"] == "[REDACTED]"
    assert event.metadata["raw_prompt"] == "[REDACTED]"
    assert event.metadata["safe"] == "line one line two"
    assert event.metadata["nested"] == {"passenger_name": "[REDACTED]"}


def test_trace_jsonl_export_is_reproducible(tmp_path: Path) -> None:
    event = TraceEvent(
        trace_id="trace-1",
        span_id="span-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind=TraceKind.EVALUATION_CASE,
        name="evaluation.case",
        status="succeeded",
        case_reference=safe_reference("CASE-0001"),
    )
    path = tmp_path / "trace.jsonl"
    export_jsonl([event], path)
    assert inspect_jsonl(path)[0]["case_reference"] != "CASE-0001"
