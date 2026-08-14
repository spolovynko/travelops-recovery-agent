"""Map context builds into the existing privacy-safe trace schema."""

from travelops_recovery_agent.context_engineering.models import ContextBuildResult
from travelops_recovery_agent.observability import TraceEvent, TraceKind, safe_reference


def context_trace_events(
    result: ContextBuildResult,
    *,
    trace_id: str,
    request_id: str | None = None,
    workflow_run_id: str | None = None,
    evaluation_case_id: str | None = None,
) -> tuple[TraceEvent, TraceEvent]:
    return (
        TraceEvent(
            trace_id=trace_id,
            request_id=request_id,
            workflow_run_id=workflow_run_id,
            case_reference=safe_reference(result.case_id),
            evaluation_case_id=evaluation_case_id,
            span_id=f"{result.build_id}:start",
            kind=TraceKind.CONTEXT_BUILD,
            name="context.build",
            status="started",
            metadata={
                "schema_version": result.schema_version,
                "policy_version": result.policy_version,
                "task": result.task.value,
                "workflow_node": result.workflow_node,
            },
        ),
        TraceEvent(
            trace_id=trace_id,
            request_id=request_id,
            workflow_run_id=workflow_run_id,
            case_reference=safe_reference(result.case_id),
            evaluation_case_id=evaluation_case_id,
            span_id=f"{result.build_id}:complete",
            parent_span_id=f"{result.build_id}:start",
            kind=TraceKind.CONTEXT_BUILD,
            name="context.build",
            status=("succeeded" if result.status.value == "ready" else "interrupted"),
            duration_ms=result.selection_latency_ms,
            metadata={
                "selected_count": len(result.selected),
                "rejected_count": result.excluded_count,
                "budget": result.token_accounting.budget,
                "selected_token_estimate": result.token_accounting.selected_estimate,
                "tool_schema_estimate": result.token_accounting.tool_schema_estimate,
                "estimate_method": result.token_accounting.estimate_method,
                "cache_hit": result.cache.hit,
                "conflict_count": result.conflict_count,
                "tools_exposed": sum(tool.exposed for tool in result.tools),
                "tools_denied": sum(not tool.exposed for tool in result.tools),
                "safe_escalation": result.escalation_reason is not None,
            },
        ),
    )
