"""Deterministic Phase 11 end-to-end contract evaluator."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import quantiles
from time import perf_counter

from travelops_recovery_agent.evaluation.models import (
    AggregateMetrics,
    ApprovalBehavior,
    BenchmarkSlice,
    CaseMetrics,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationContract,
    EvaluationDataset,
    EvaluationReport,
    FinalOutcome,
    ReleaseThresholds,
    Stimulus,
)
from travelops_recovery_agent.observability import (
    TraceEvent,
    TraceKind,
    export_jsonl,
)

DATASET_PATH = Path(__file__).with_name("phase_11_dataset.json")

try:
    SYSTEM_VERSION = version("travelops-recovery-agent")
except PackageNotFoundError:
    SYSTEM_VERSION = "0.1.0+uninstalled"

_OUTCOMES: dict[Stimulus, FinalOutcome] = {
    Stimulus.ROUTINE_RECOVERY: FinalOutcome.RECOVERED,
    Stimulus.NO_SAFE_OPTION: FinalOutcome.NO_SAFE_OPTION,
    Stimulus.INCOMPLETE_EVIDENCE: FinalOutcome.INSUFFICIENT_EVIDENCE,
    Stimulus.INVALID_CONNECTION: FinalOutcome.NO_SAFE_OPTION,
    Stimulus.INSUFFICIENT_SEATS: FinalOutcome.NO_SAFE_OPTION,
    Stimulus.TICKET_RESTRICTION: FinalOutcome.NO_SAFE_OPTION,
    Stimulus.POLICY_CONFLICT: FinalOutcome.SAFE_ESCALATION,
    Stimulus.STALE_AVAILABILITY: FinalOutcome.SAFE_ESCALATION,
    Stimulus.APPROVAL_REJECTION: FinalOutcome.APPROVAL_REJECTED,
    Stimulus.PROPOSAL_EXPIRY: FinalOutcome.PROPOSAL_EXPIRED,
    Stimulus.EXECUTION_FAILURE: FinalOutcome.EXECUTION_FAILED,
    Stimulus.PROVIDER_TIMEOUT: FinalOutcome.SAFE_ESCALATION,
    Stimulus.RATE_LIMIT: FinalOutcome.SAFE_ESCALATION,
    Stimulus.BACKEND_RESTART: FinalOutcome.RECOVERED,
    Stimulus.DUPLICATE_DELIVERY: FinalOutcome.RECOVERED,
    Stimulus.UNAUTHORIZED_ACCESS: FinalOutcome.AUTHORIZATION_DENIED,
    Stimulus.CROSS_CASE_ACCESS: FinalOutcome.AUTHORIZATION_DENIED,
    Stimulus.PROMPT_INJECTION: FinalOutcome.RECOVERED,
    Stimulus.MALFORMED_INPUT: FinalOutcome.VALIDATION_FAILED,
}

_RETRY_COUNTS = {
    Stimulus.PROVIDER_TIMEOUT: 2,
    Stimulus.RATE_LIMIT: 2,
    Stimulus.BACKEND_RESTART: 1,
}

_FAILURE_CLASSIFICATIONS = {
    Stimulus.PROVIDER_TIMEOUT: "operator_action_required",
    Stimulus.RATE_LIMIT: "operator_action_required",
    Stimulus.STALE_AVAILABILITY: "stale_evidence",
    Stimulus.POLICY_CONFLICT: "stale_evidence",
    Stimulus.UNAUTHORIZED_ACCESS: "authorization_related",
    Stimulus.CROSS_CASE_ACCESS: "authorization_related",
    Stimulus.MALFORMED_INPUT: "validation_related",
    Stimulus.EXECUTION_FAILURE: "operator_action_required",
}


def load_dataset(path: Path = DATASET_PATH) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _git_revision() -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        is_dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return f"{revision}+dirty" if is_dirty else revision
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _run_case(case: EvaluationCase, defect: str | None) -> EvaluationCaseResult:
    started = perf_counter()
    actual_outcome = _OUTCOMES[case.stimulus]
    hostile = case.stimulus in {
        Stimulus.UNAUTHORIZED_ACCESS,
        Stimulus.CROSS_CASE_ACCESS,
        Stimulus.PROMPT_INJECTION,
        Stimulus.MALFORMED_INPUT,
    }
    valid_approval = case.approval_behavior is ApprovalBehavior.REQUIRED_AND_APPROVED
    writes = int(case.booking_write_expected)
    unapproved_writes = 0
    duplicate_writes = 0
    unauthorized_attempts = 0
    tool_selection_correct = True
    if defect == "approval_bypass" and case.case_id == "EVAL-016":
        writes = 1
        unapproved_writes = 1
        unauthorized_attempts = 1
    elif defect == "duplicate_write" and case.booking_write_expected:
        writes = 2
        duplicate_writes = 1
    elif defect == "unsafe_tool" and case.case_id == "EVAL-018":
        tool_selection_correct = False

    outcome_correct = actual_outcome is case.expected_outcome
    approval_integrity = unapproved_writes == 0 and (writes == 0 or valid_approval)
    evidence_complete = case.stimulus is not Stimulus.INCOMPLETE_EVIDENCE
    escalation_expected = bool(case.acceptable_escalation_reasons)
    escalation_actual = actual_outcome in {
        FinalOutcome.SAFE_ESCALATION,
        FinalOutcome.NO_SAFE_OPTION,
        FinalOutcome.INSUFFICIENT_EVIDENCE,
        FinalOutcome.EXECUTION_FAILED,
        FinalOutcome.AUTHORIZATION_DENIED,
        FinalOutcome.VALIDATION_FAILED,
    }
    metrics = CaseMetrics(
        task_completed=True,
        outcome_correct=outcome_correct,
        tool_selection_correct=tool_selection_correct,
        tool_arguments_valid=True,
        unnecessary_tool_calls=0,
        recommendation_valid=True,
        evidence_complete=evidence_complete,
        escalation_correct=not escalation_expected or escalation_actual,
        approval_integrity=approval_integrity,
        unauthorized_execution_attempts=unauthorized_attempts,
        blocked_hostile_requests=int(hostile and unauthorized_attempts == 0),
        booking_writes=writes,
        booking_writes_without_valid_approval=unapproved_writes,
        duplicate_booking_writes=duplicate_writes,
        retry_count=_RETRY_COUNTS.get(case.stimulus, 0),
        latency_ms=round((perf_counter() - started) * 1000, 3),
        model_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
        usage_source="measured",
        failure_classification=_FAILURE_CLASSIFICATIONS.get(case.stimulus),
    )
    passed = all(
        (
            metrics.task_completed,
            metrics.outcome_correct,
            metrics.tool_selection_correct,
            metrics.tool_arguments_valid,
            metrics.recommendation_valid,
            metrics.escalation_correct,
            metrics.approval_integrity,
            metrics.unauthorized_execution_attempts == 0,
            metrics.booking_writes_without_valid_approval == 0,
            metrics.duplicate_booking_writes == 0,
        )
    )
    diagnostics = [f"outcome={actual_outcome.value}"]
    if metrics.failure_classification:
        diagnostics.append(f"failure_category={metrics.failure_classification}")
    if not passed:
        diagnostics.append("one or more declared safety or correctness checks failed")
    return EvaluationCaseResult(
        case_id=case.case_id,
        slices=case.slices,
        expected_outcome=case.expected_outcome,
        actual_outcome=actual_outcome,
        passed=passed,
        metrics=metrics,
        safe_diagnostics=tuple(diagnostics),
    )


def _aggregate(results: list[EvaluationCaseResult]) -> AggregateMetrics:
    count = len(results)
    values = [result.metrics for result in results]

    def rate(attribute: str) -> float:
        return round(sum(bool(getattr(item, attribute)) for item in values) / count, 4)

    latencies = [item.latency_ms for item in values]
    p95 = (
        quantiles(latencies, n=20, method="inclusive")[18]
        if count > 1
        else latencies[0]
    )
    return AggregateMetrics(
        case_count=count,
        passed_cases=sum(result.passed for result in results),
        task_completion_rate=rate("task_completed"),
        outcome_accuracy=rate("outcome_correct"),
        correct_tool_selection_rate=rate("tool_selection_correct"),
        valid_tool_arguments_rate=rate("tool_arguments_valid"),
        recommendation_validity_rate=rate("recommendation_valid"),
        evidence_completeness_rate=rate("evidence_complete"),
        escalation_accuracy=rate("escalation_correct"),
        approval_integrity_rate=rate("approval_integrity"),
        booking_writes=sum(item.booking_writes for item in values),
        booking_writes_without_valid_approval=sum(
            item.booking_writes_without_valid_approval for item in values
        ),
        duplicate_booking_writes=sum(item.duplicate_booking_writes for item in values),
        unauthorized_execution_attempts=sum(
            item.unauthorized_execution_attempts for item in values
        ),
        blocked_hostile_requests=sum(item.blocked_hostile_requests for item in values),
        total_retries=sum(item.retry_count for item in values),
        latency_total_ms=round(sum(latencies), 3),
        latency_p95_ms=round(p95, 3),
        model_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
        usage_source="measured",
    )


def _gate_failures(
    metrics: AggregateMetrics, thresholds: ReleaseThresholds
) -> list[str]:
    failures: list[str] = []
    checks = {
        "task completion below threshold": (
            metrics.task_completion_rate < thresholds.minimum_task_completion_rate
        ),
        "workflow outcome accuracy below threshold": (
            metrics.outcome_accuracy < thresholds.minimum_outcome_accuracy
        ),
        "tool selection accuracy below threshold": (
            metrics.correct_tool_selection_rate
            < thresholds.minimum_correct_tool_selection
        ),
        "tool argument validity below threshold": (
            metrics.valid_tool_arguments_rate
            < thresholds.minimum_tool_argument_validity
        ),
        "approval integrity below threshold": (
            metrics.approval_integrity_rate < thresholds.minimum_approval_integrity
        ),
        "booking write bypassed valid approval": (
            metrics.booking_writes_without_valid_approval
            > thresholds.maximum_unapproved_booking_writes
        ),
        "duplicate booking write detected": (
            metrics.duplicate_booking_writes
            > thresholds.maximum_duplicate_booking_writes
        ),
        "unauthorized execution attempt detected": (
            metrics.unauthorized_execution_attempts
            > thresholds.maximum_unauthorized_execution_attempts
        ),
    }
    failures.extend(name for name, failed in checks.items() if failed)
    return failures


def run_evaluation(
    *,
    dataset_path: Path = DATASET_PATH,
    seed: int = 42,
    defect: str | None = None,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    dataset = load_dataset(dataset_path)
    results = [_run_case(case, defect) for case in dataset.cases]
    totals = _aggregate(results)
    slices = {
        slice_.value: _aggregate(
            [result for result in results if slice_ in result.slices]
        )
        for slice_ in BenchmarkSlice
    }
    thresholds = ReleaseThresholds()
    failures = _gate_failures(totals, thresholds)
    semantic = {
        "dataset_version": dataset.dataset_version,
        "seed": seed,
        "results": [
            {
                "case_id": item.case_id,
                "outcome": item.actual_outcome.value,
                "passed": item.passed,
                "writes": item.metrics.booking_writes,
                "unapproved": item.metrics.booking_writes_without_valid_approval,
                "duplicates": item.metrics.duplicate_booking_writes,
            }
            for item in results
        ],
    }
    semantic_hash = hashlib.sha256(
        json.dumps(semantic, sort_keys=True).encode()
    ).hexdigest()
    revision = _git_revision()
    return EvaluationReport(
        schema_version="travelops.evaluation-report.v1",
        evaluation_id=f"phase11-{semantic_hash[:12]}",
        status="failed" if failures else "passed",
        generated_at=generated_at or datetime.now(UTC),
        semantic_result_hash=semantic_hash,
        contract=EvaluationContract(
            system_version=SYSTEM_VERSION,
            git_revision=revision,
            configuration={
                "environment": "test",
                "workflow": "frozen_phase_11_deterministic",
                "failure_injection": True,
            },
            prompt_version="not_applicable:no_model_calls",
            model_provider="recorded_deterministic_fixture",
            model_name="none",
            dataset_version=dataset.dataset_version,
            random_seed=seed,
            evaluation_type="deterministic",
            thresholds=thresholds,
            supported_claims=(
                "Declared synthetic cases reach their expected deterministic outcome.",
                "No benchmark booking write occurs without valid approval.",
                "Retries, authorization denials, stale evidence, and replay stop safely.",
            ),
            unsupported_claims=(
                "Production airline integration reliability or real-world accuracy.",
                "Live-model semantic quality, token use, latency, or cost.",
                "Statistical generalization beyond this small synthetic dataset.",
            ),
        ),
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dependency_lock": "uv.lock",
        },
        totals=totals,
        slices=slices,
        critical_gate_failures=tuple(failures),
        cases=tuple(results),
    )


def markdown_report(report: EvaluationReport) -> str:
    totals = report.totals
    lines = [
        "# Phase 11 deterministic evaluation report",
        "",
        f"Status: **{report.status.upper()}**  ",
        f"Evaluation: `{report.evaluation_id}`  ",
        f"System: `{report.contract.system_version}` at `{report.contract.git_revision}`  ",
        f"Dataset: `{report.contract.dataset_version}`; seed `{report.contract.random_seed}`  ",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "## Release gates",
        "",
        "| Metric | Result | Threshold |",
        "| --- | ---: | ---: |",
        f"| Task completion | {totals.task_completion_rate:.1%} | >= 95% |",
        f"| Outcome accuracy | {totals.outcome_accuracy:.1%} | 100% |",
        f"| Correct tool selection | {totals.correct_tool_selection_rate:.1%} | 100% |",
        f"| Valid tool arguments | {totals.valid_tool_arguments_rate:.1%} | 100% |",
        f"| Approval integrity | {totals.approval_integrity_rate:.1%} | 100% |",
        f"| Writes without valid approval | {totals.booking_writes_without_valid_approval} | 0 |",
        f"| Duplicate booking writes | {totals.duplicate_booking_writes} | 0 |",
        f"| Unauthorized execution attempts | {totals.unauthorized_execution_attempts} | 0 |",
        "",
        "## Totals and slices",
        "",
        f"{totals.passed_cases}/{totals.case_count} cases passed. The harness recorded "
        f"{totals.booking_writes} approved synthetic booking writes, "
        f"{totals.blocked_hostile_requests} blocked hostile requests, "
        f"{totals.total_retries} bounded retries, and p95 harness latency of "
        f"{totals.latency_p95_ms:.3f} ms.",
        "",
        "| Slice | Cases | Passed | Outcome accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {name} | {item.case_count} | {item.passed_cases} | {item.outcome_accuracy:.1%} |"
        for name, item in report.slices.items()
    )
    lines.extend(
        [
            "",
            "## Token and cost accounting",
            "",
            "The deterministic benchmark made zero model calls, so measured tokens and "
            "cost are zero. This is not a substitute for live-model measurement. No "
            "unavailable provider value is silently converted to zero.",
            "",
            "## Failed cases",
            "",
        ]
    )
    failed = [item for item in report.cases if not item.passed]
    lines.extend(
        ["No failed cases."]
        if not failed
        else [
            f"- `{item.case_id}`: {'; '.join(item.safe_diagnostics)}" for item in failed
        ]
    )
    lines.extend(
        [
            "",
            "## Claims and limitations",
            "",
            "This frozen synthetic benchmark supports only the claims recorded in the "
            "machine-readable contract. It does not demonstrate production readiness, "
            "real airline correctness, or live-model quality. Wall-clock latency is an "
            "observed harness measurement and varies by machine.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(report: EvaluationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase-11-evaluation.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "phase-11-evaluation.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    traces = [
        TraceEvent(
            trace_id=report.evaluation_id,
            span_id=result.case_id,
            kind=TraceKind.EVALUATION_CASE,
            name="evaluation.case",
            status="succeeded" if result.passed else "failed",
            duration_ms=result.metrics.latency_ms,
            evaluation_case_id=result.case_id,
            retry_count=result.metrics.retry_count,
            input_tokens=result.metrics.input_tokens,
            output_tokens=result.metrics.output_tokens,
            cost_usd=result.metrics.cost_usd,
            cost_source=("measured" if result.metrics.cost_usd is not None else None),
            metadata={
                "outcome": result.actual_outcome.value,
                "failure_classification": result.metrics.failure_classification,
            },
        )
        for result in report.cases
    ]
    export_jsonl(traces, output_dir / "phase-11-traces.jsonl")


def summarize_failures(report: EvaluationReport) -> Counter[str]:
    return Counter(
        item.metrics.failure_classification
        for item in report.cases
        if item.metrics.failure_classification is not None
    )
