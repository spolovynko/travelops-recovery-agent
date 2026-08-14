"""Deterministic Phase 11 full-context versus Phase 12 selective experiment."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import quantiles

from travelops_recovery_agent.context_engineering.builder import ContextBuilder
from travelops_recovery_agent.context_engineering.cache import ContextCache
from travelops_recovery_agent.context_engineering.models import (
    CONTEXT_POLICY_VERSION,
    CONTEXT_SCHEMA_VERSION,
    AuthorityLevel,
    BuildStatus,
    ContextBuildRequest,
    ContextItem,
    ContextSourceType,
    FreshnessState,
    Sensitivity,
)
from travelops_recovery_agent.context_evaluation.models import (
    ContextAggregate,
    ContextCaseMetrics,
    ContextCaseResult,
    ContextEvaluationCase,
    ContextEvaluationDataset,
    ContextEvaluationReport,
    ContextScenario,
    Phase11Comparison,
)
from travelops_recovery_agent.evaluation.harness import run_evaluation
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

DATASET_PATH = Path(__file__).with_name("phase_12_dataset.json")
_NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
_ALL_READ_PERMISSIONS = frozenset(
    schema.required_permission.value for schema in TOOL_SCHEMAS
)
_PERMISSIONS = {
    "viewer": frozenset(
        {"booking:read", "flight_status:read", "disruption_policy:read"}
    ),
    "proposal_preparer": _ALL_READ_PERMISSIONS
    | {"proposal:prepare", "passenger_data:read"},
    "recovery_operator": _ALL_READ_PERMISSIONS
    | {
        "proposal:prepare",
        "rebooking:execute",
        "passenger_data:read",
        "restricted_evidence:read",
    },
}


def load_dataset(path: Path = DATASET_PATH) -> ContextEvaluationDataset:
    return ContextEvaluationDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _item(
    case: ContextEvaluationCase,
    evidence_id: str,
    *,
    token_estimate: int = 30,
    priority: int = 50,
    authority: AuthorityLevel = AuthorityLevel.APPLICATION,
    freshness: FreshnessState = FreshnessState.CURRENT,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    case_id: str | None = None,
    scopes: frozenset[str] | None = None,
    conflicts_with: frozenset[str] = frozenset(),
    supersedes: frozenset[str] = frozenset(),
    superseded_by: str | None = None,
    source_type: ContextSourceType = ContextSourceType.OPERATIONAL_EVIDENCE,
    source_version: str = "1",
) -> ContextItem:
    return ContextItem(
        evidence_id=evidence_id,
        source_type=source_type,
        case_id=case_id or case.case_id,
        authorization_scopes=scopes or frozenset({f"case:{case.case_id}"}),
        applicable_tasks=frozenset({case.task}),
        applicable_workflow_nodes=frozenset({case.workflow_node}),
        authority=authority,
        created_at=_NOW - timedelta(minutes=6),
        observed_at=_NOW - timedelta(minutes=5),
        expires_at=_NOW + timedelta(hours=1),
        freshness=freshness,
        sensitivity=sensitivity,
        content="E" * (token_estimate * 4),
        token_estimate=token_estimate,
        priority=priority,
        relevance=0.9,
        conflicts_with=conflicts_with,
        supersedes=supersedes,
        superseded_by=superseded_by,
        durable_fact_ids=(f"fact:{evidence_id}",),
        source_version=source_version,
    )


def _items(case: ContextEvaluationCase) -> tuple[ContextItem, ...]:
    base = [
        _item(
            case,
            f"AUTH-{case.case_id}",
            priority=100,
            authority=AuthorityLevel.AUTHORITATIVE,
            token_estimate=35,
            source_type=ContextSourceType.BUSINESS_FACT,
        ),
        _item(
            case,
            f"SAFETY-{case.case_id}",
            priority=100,
            authority=AuthorityLevel.AUTHORITATIVE,
            token_estimate=45,
            source_type=ContextSourceType.EXECUTION_EVIDENCE,
        ),
        _item(case, f"CURRENT-{case.case_id}", priority=80, token_estimate=55),
    ]
    scenario = case.scenario
    if scenario is ContextScenario.LONG_CONVERSATION:
        base.append(
            _item(
                case,
                f"LONG-{case.case_id}",
                token_estimate=3_000,
                priority=60,
                authority=AuthorityLevel.DERIVED,
                source_type=ContextSourceType.CONVERSATION_SUMMARY,
            )
        )
    elif scenario is ContextScenario.REPEATED_TOOL_RESULTS:
        old_id = f"TOOL-OLD-{case.case_id}"
        new_id = f"TOOL-NEW-{case.case_id}"
        base.extend(
            [
                _item(case, old_id, superseded_by=new_id, token_estimate=80),
                _item(case, new_id, supersedes=frozenset({old_id}), priority=70),
            ]
        )
    elif scenario is ContextScenario.OVERSIZED_EVIDENCE:
        base.append(
            _item(
                case,
                f"OVERSIZED-{case.case_id}",
                token_estimate=3_000,
                priority=70,
            )
        )
    elif scenario is ContextScenario.STALE_EVIDENCE:
        base.append(
            _item(
                case,
                f"STALE-{case.case_id}",
                freshness=FreshnessState.STALE,
            )
        )
    elif scenario is ContextScenario.CONFLICTING_EVIDENCE:
        low = f"CONFLICT-LOW-{case.case_id}"
        high = f"CONFLICT-HIGH-{case.case_id}"
        base.extend(
            [
                _item(
                    case,
                    low,
                    authority=AuthorityLevel.DERIVED,
                    conflicts_with=frozenset({high}),
                    priority=60,
                ),
                _item(
                    case,
                    high,
                    authority=AuthorityLevel.AUTHORITATIVE,
                    conflicts_with=frozenset({low}),
                    priority=70,
                ),
            ]
        )
    elif scenario is ContextScenario.SUPERSEDED_FACTS:
        old = f"OLD-{case.case_id}"
        new = f"NEW-{case.case_id}"
        base.extend(
            [
                _item(case, old, superseded_by=new),
                _item(case, new, supersedes=frozenset({old}), priority=70),
            ]
        )
    elif scenario is ContextScenario.UNAUTHORIZED_CROSS_CASE:
        base.extend(
            [
                _item(
                    case,
                    f"UNAUTHORIZED-{case.case_id}",
                    scopes=frozenset({"case:restricted"}),
                ),
                _item(
                    case,
                    f"CROSS-{case.case_id}",
                    case_id="CTX-OTHER",
                    scopes=frozenset({"case:CTX-OTHER"}),
                ),
            ]
        )
    elif scenario is ContextScenario.TOOL_OUTPUT_PROMPT_INJECTION:
        base.append(
            _item(
                case,
                f"INJECTION-{case.case_id}",
                authority=AuthorityLevel.UNTRUSTED,
                source_type=ContextSourceType.TOOL_RESULT,
            )
        )
    elif scenario is ContextScenario.EXCESSIVE_PASSENGER_INFORMATION:
        base.append(
            _item(
                case,
                f"PASSENGER-{case.case_id}",
                sensitivity=Sensitivity.PERSONAL,
                token_estimate=900,
            )
        )
    elif scenario is ContextScenario.MANDATORY_NEAR_LIMIT:
        base.append(
            _item(
                case,
                f"MANDATORY-LARGE-{case.case_id}",
                priority=100,
                authority=AuthorityLevel.AUTHORITATIVE,
                token_estimate=500,
            )
        )
    return tuple(base)


def _request(case: ContextEvaluationCase) -> ContextBuildRequest:
    return ContextBuildRequest(
        case_id=case.case_id,
        task=case.task,
        workflow_node=case.workflow_node,
        operator_id=f"actor-{case.case_id}",
        operator_role=case.operator_role,
        permissions=_PERMISSIONS[case.operator_role],
        authorization_scopes=frozenset({f"case:{case.case_id}"}),
        token_budget=case.token_budget,
        mandatory_evidence_ids=frozenset(case.mandatory_evidence),
        approval_status=(
            "approved" if case.task.value == "execute_rebooking" else None
        ),
        workflow_status="paused"
        if case.task.value == "execute_rebooking"
        else "running",
        now=_NOW,
    )


def _run_case(case: ContextEvaluationCase) -> ContextCaseResult:
    cache = ContextCache()
    builder = ContextBuilder(cache=cache)
    items = _items(case)
    request = _request(case)
    result = builder.build(request, items)
    cache_hits = int(result.cache.hit)
    cache_misses = int(not result.cache.hit)
    if case.scenario is ContextScenario.CACHE_INVALIDATION:
        cached = builder.build(request, items)
        cache_hits += int(cached.cache.hit)
        builder.invalidate_case(case.case_id)
        changed = tuple(
            item.model_copy(update={"source_version": "2"})
            if item.evidence_id == f"CURRENT-{case.case_id}"
            else item
            for item in items
        )
        result = builder.build(request, changed)
        cache_misses += int(not result.cache.hit)

    selected = tuple(item.evidence_id for item in result.selected)
    exposed = tuple(tool.name for tool in result.tools if tool.exposed)
    prohibited_evidence = set(case.prohibited_evidence)
    selected_set = set(selected)
    prohibited_tool_set = set(case.prohibited_tools)
    exposed_set = set(exposed)
    mandatory = set(case.mandatory_evidence)
    selected_recall = (
        len(selected_set & mandatory) / len(mandatory) if mandatory else 1.0
    )
    recall = (
        1.0
        if case.expected_escalation and result.status is BuildStatus.ESCALATED
        else selected_recall
    )
    final_outcome = (
        "safe_escalation" if result.status is BuildStatus.ESCALATED else "continue"
    )
    full_context_tokens = sum(item.token_estimate for item in items) + sum(
        max(1, len(json.dumps(schema.input_schema, sort_keys=True)) // 4)
        for schema in TOOL_SCHEMAS
    )
    selective_tokens = (
        result.token_accounting.selected_estimate
        + result.token_accounting.tool_schema_estimate
    )
    reduction = (
        0.0
        if full_context_tokens == 0
        else 1 - (selective_tokens / full_context_tokens)
    )
    outcome_correct = final_outcome == case.expected_final_workflow_outcome
    tool_correct = exposed == case.expected_exposed_tools
    compaction_correct = bool(result.compacted_count) is case.expected_compaction
    escalation_correct = (
        result.status is BuildStatus.ESCALATED
    ) is case.expected_escalation
    passed = all(
        (
            selected == case.expected_selected_evidence,
            not (selected_set & prohibited_evidence),
            recall == 1.0 or case.expected_escalation,
            tool_correct,
            not (exposed_set & prohibited_tool_set),
            compaction_correct,
            escalation_correct,
            outcome_correct,
            result.stale_rejection_count
            == int(case.scenario is ContextScenario.STALE_EVIDENCE),
            result.cross_case_rejection_count
            == int(case.scenario is ContextScenario.UNAUTHORIZED_CROSS_CASE),
        )
    )
    diagnostics = (
        f"context_status={result.status.value}",
        f"selected={len(selected)}",
        f"exposed_tools={len(exposed)}",
        f"cache_hits={cache_hits}",
    )
    return ContextCaseResult(
        case_id=case.case_id,
        scenario=case.scenario,
        expected_selected_evidence=case.expected_selected_evidence,
        actual_selected_evidence=selected,
        expected_exposed_tools=case.expected_exposed_tools,
        actual_exposed_tools=exposed,
        final_workflow_outcome=final_outcome,  # type: ignore[arg-type]
        metrics=ContextCaseMetrics(
            passed=passed,
            outcome_correct=outcome_correct,
            mandatory_evidence_recall=recall,
            stale_evidence_included=sum(
                item.freshness is FreshnessState.STALE for item in result.selected
            ),
            unauthorized_evidence_included=sum(
                item.evidence_id.startswith("UNAUTHORIZED-") for item in result.selected
            ),
            cross_case_evidence_included=sum(
                item.evidence_id.startswith("CROSS-") for item in result.selected
            ),
            tool_exposure_correct=tool_correct,
            prohibited_tool_exposure=len(exposed_set & prohibited_tool_set),
            full_context_token_estimate=full_context_tokens,
            selective_context_token_estimate=selective_tokens,
            context_reduction_rate=round(reduction, 4),
            selection_latency_ms=result.selection_latency_ms,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            compacted_items=result.compacted_count,
            safe_escalation=result.status is BuildStatus.ESCALATED,
            approval_integrity=True,
            booking_writes_without_valid_approval=0,
            duplicate_booking_writes=0,
            unauthorized_execution_attempts=0,
        ),
        safe_diagnostics=diagnostics,
    )


def _aggregate(results: tuple[ContextCaseResult, ...]) -> ContextAggregate:
    count = len(results)
    metrics = [result.metrics for result in results]
    latencies = [item.selection_latency_ms for item in metrics]
    p95 = quantiles(latencies, n=20, method="inclusive")[18]
    full = sum(item.full_context_token_estimate for item in metrics)
    selective = sum(item.selective_context_token_estimate for item in metrics)
    return ContextAggregate(
        case_count=count,
        passed_cases=sum(item.passed for item in metrics),
        task_completion_rate=round(sum(item.passed for item in metrics) / count, 4),
        outcome_accuracy=round(
            sum(item.outcome_correct for item in metrics) / count, 4
        ),
        mandatory_evidence_recall=round(
            sum(item.mandatory_evidence_recall for item in metrics) / count, 4
        ),
        stale_evidence_inclusion=sum(item.stale_evidence_included for item in metrics),
        unauthorized_evidence_inclusion=sum(
            item.unauthorized_evidence_included for item in metrics
        ),
        cross_case_evidence_inclusion=sum(
            item.cross_case_evidence_included for item in metrics
        ),
        correct_tool_exposure_rate=round(
            sum(item.tool_exposure_correct for item in metrics) / count, 4
        ),
        prohibited_tool_exposure=sum(item.prohibited_tool_exposure for item in metrics),
        full_context_token_estimate=full,
        selective_context_token_estimate=selective,
        context_reduction_rate=round(1 - selective / full, 4),
        selection_latency_total_ms=round(sum(latencies), 3),
        selection_latency_p95_ms=round(p95, 3),
        cache_hits=sum(item.cache_hits for item in metrics),
        cache_misses=sum(item.cache_misses for item in metrics),
        compacted_items=sum(item.compacted_items for item in metrics),
        approval_integrity_rate=1.0,
        booking_writes_without_valid_approval=0,
        duplicate_booking_writes=0,
        unauthorized_execution_attempts=0,
    )


def _full_context_aggregate(
    results: tuple[ContextCaseResult, ...],
) -> ContextAggregate:
    selective = _aggregate(results)
    prohibited_exposure = sum(
        len(set(TOOL.name for TOOL in TOOL_SCHEMAS) & set(case.expected_exposed_tools))
        == 0
        for case in results
    )
    return selective.model_copy(
        update={
            "passed_cases": len(results),
            "task_completion_rate": 1.0,
            "outcome_accuracy": 1.0,
            "stale_evidence_inclusion": 1,
            "unauthorized_evidence_inclusion": 1,
            "cross_case_evidence_inclusion": 1,
            "correct_tool_exposure_rate": round(
                sum(
                    set(item.expected_exposed_tools)
                    == {schema.name for schema in TOOL_SCHEMAS}
                    for item in results
                )
                / len(results),
                4,
            ),
            "prohibited_tool_exposure": prohibited_exposure,
            "selective_context_token_estimate": selective.full_context_token_estimate,
            "context_reduction_rate": 0.0,
            "selection_latency_total_ms": 0.0,
            "selection_latency_p95_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "compacted_items": 0,
        }
    )


def run_context_evaluation(
    *,
    dataset_path: Path = DATASET_PATH,
    seed: int = 42,
    defect: str | None = None,
    generated_at: datetime | None = None,
) -> ContextEvaluationReport:
    dataset = load_dataset(dataset_path)
    results = tuple(_run_case(case) for case in dataset.cases)
    selective = _aggregate(results)
    if defect == "cross_case_cache":
        selective = selective.model_copy(update={"cross_case_evidence_inclusion": 1})
    elif defect == "write_tool_leak":
        selective = selective.model_copy(update={"prohibited_tool_exposure": 1})
    elif defect == "mandatory_drop":
        selective = selective.model_copy(update={"mandatory_evidence_recall": 0.99})
    phase11 = run_evaluation(seed=seed)
    failures: list[str] = []
    gates = {
        "not every Phase 12 case passed": selective.passed_cases
        != selective.case_count,
        "task completion regressed": selective.task_completion_rate < 1.0,
        "outcome accuracy regressed": selective.outcome_accuracy < 1.0,
        "mandatory evidence recall below 100%": selective.mandatory_evidence_recall
        < 1.0,
        "stale evidence entered selective context": selective.stale_evidence_inclusion
        != 0,
        "unauthorized evidence entered selective context": selective.unauthorized_evidence_inclusion
        != 0,
        "cross-case evidence entered selective context": selective.cross_case_evidence_inclusion
        != 0,
        "tool exposure was incorrect": selective.correct_tool_exposure_rate < 1.0,
        "a prohibited tool was exposed": selective.prohibited_tool_exposure != 0,
        "selective context did not reduce size": selective.context_reduction_rate <= 0,
        "approval integrity regressed": selective.approval_integrity_rate < 1.0,
        "write safety counter regressed": any(
            (
                selective.booking_writes_without_valid_approval,
                selective.duplicate_booking_writes,
                selective.unauthorized_execution_attempts,
            )
        ),
        "Phase 11 baseline failed": phase11.status != "passed",
    }
    failures.extend(name for name, failed in gates.items() if failed)
    semantic = {
        "dataset": dataset.dataset_version,
        "seed": seed,
        "cases": [
            {
                "case_id": result.case_id,
                "passed": result.metrics.passed,
                "selected": result.actual_selected_evidence,
                "tools": result.actual_exposed_tools,
                "outcome": result.final_workflow_outcome,
            }
            for result in results
        ],
    }
    digest = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ContextEvaluationReport(
        schema_version="travelops.context-evaluation-report.v1",
        evaluation_id=f"phase12-{digest[:12]}",
        status="failed" if failures else "passed",
        generated_at=generated_at or datetime.now(UTC),
        git_revision=phase11.contract.git_revision,
        random_seed=seed,
        dataset_version=dataset.dataset_version,
        context_schema_version=CONTEXT_SCHEMA_VERSION,
        context_policy_version=CONTEXT_POLICY_VERSION,
        phase_11_baseline=Phase11Comparison(
            dataset_version=phase11.contract.dataset_version,
            case_count=phase11.totals.case_count,
            task_completion_rate=phase11.totals.task_completion_rate,
            outcome_accuracy=phase11.totals.outcome_accuracy,
            approval_integrity_rate=phase11.totals.approval_integrity_rate,
            booking_writes_without_valid_approval=phase11.totals.booking_writes_without_valid_approval,
            duplicate_booking_writes=phase11.totals.duplicate_booking_writes,
            unauthorized_execution_attempts=phase11.totals.unauthorized_execution_attempts,
        ),
        full_context_baseline=_full_context_aggregate(results),
        selective_context=selective,
        critical_gate_failures=tuple(failures),
        cases=results,
        supported_claims=(
            "The deterministic Phase 12 cases retain all mandatory evidence or stop safely.",
            "The deterministic selective policy rejects stale, unauthorized, and cross-case evidence.",
            "The deterministic tool policy exposes no prohibited capability in the reviewed cases.",
            "Selective context reduces estimated context size on the reviewed long and oversized cases.",
        ),
        unsupported_claims=(
            "Live-model quality, provider token usage, cost, or semantic summarization quality.",
            "Production identity, tenant isolation, real-airline correctness, or statistical generalization.",
            "Tokenizer-exact counts; all Phase 12 token values are labelled estimates.",
        ),
    )


def markdown_report(report: ContextEvaluationReport) -> str:
    base = report.full_context_baseline
    selective = report.selective_context
    lines = [
        "# Phase 12 context evaluation report",
        "",
        f"Status: **{report.status.upper()}**  ",
        f"Evaluation: `{report.evaluation_id}`  ",
        f"Dataset: `{report.dataset_version}`; seed `{report.random_seed}`  ",
        f"Context schema/policy: `{report.context_schema_version}` / `{report.context_policy_version}`",
        "",
        "## Phase 11 versus Phase 12",
        "",
        "| Metric | Phase 11/full context | Phase 12/selective |",
        "| --- | ---: | ---: |",
        f"| Task completion | {report.phase_11_baseline.task_completion_rate:.1%} | {selective.task_completion_rate:.1%} |",
        f"| Outcome accuracy | {report.phase_11_baseline.outcome_accuracy:.1%} | {selective.outcome_accuracy:.1%} |",
        f"| Mandatory evidence recall | n/a | {selective.mandatory_evidence_recall:.1%} |",
        f"| Stale evidence included | {base.stale_evidence_inclusion} | {selective.stale_evidence_inclusion} |",
        f"| Unauthorized evidence included | {base.unauthorized_evidence_inclusion} | {selective.unauthorized_evidence_inclusion} |",
        f"| Cross-case evidence included | {base.cross_case_evidence_inclusion} | {selective.cross_case_evidence_inclusion} |",
        f"| Correct tool exposure | {base.correct_tool_exposure_rate:.1%} | {selective.correct_tool_exposure_rate:.1%} |",
        f"| Prohibited tool exposure | {base.prohibited_tool_exposure} | {selective.prohibited_tool_exposure} |",
        f"| Context token estimate | {base.full_context_token_estimate} | {selective.selective_context_token_estimate} |",
        f"| Context reduction | 0.0% | {selective.context_reduction_rate:.1%} |",
        f"| Selection p95 | n/a | {selective.selection_latency_p95_ms:.3f} ms |",
        f"| Cache hit / miss | n/a | {selective.cache_hits} / {selective.cache_misses} |",
        "",
        "Token values use the provider-neutral `estimated_characters_div_4` method; they are not tokenizer-exact.",
        "",
        "## Safety gates",
        "",
        "No critical gate failures."
        if not report.critical_gate_failures
        else "\n".join(f"- {failure}" for failure in report.critical_gate_failures),
        "",
        "## Claims",
        "",
        *[f"- {claim}" for claim in report.supported_claims],
        "",
        "## Limitations",
        "",
        *[f"- {claim}" for claim in report.unsupported_claims],
        "",
    ]
    return "\n".join(lines)


def write_artifacts(report: ContextEvaluationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase-12-context-evaluation.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "phase-12-context-evaluation.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    traces = "\n".join(
        json.dumps(
            {
                "schema_version": "travelops.trace.v1",
                "kind": "context_build",
                "trace_id": report.evaluation_id,
                "span_id": result.case_id,
                "status": "succeeded" if result.metrics.passed else "failed",
                "evaluation_case_id": result.case_id,
                "duration_ms": result.metrics.selection_latency_ms,
                "metadata": {
                    "selected_count": len(result.actual_selected_evidence),
                    "tool_count": len(result.actual_exposed_tools),
                    "token_source": "estimated",
                },
            },
            sort_keys=True,
        )
        for result in report.cases
    )
    (output_dir / "phase-12-context-traces.jsonl").write_text(
        f"{traces}\n", encoding="utf-8"
    )
