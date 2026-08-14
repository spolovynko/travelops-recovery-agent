from datetime import UTC, datetime
from pathlib import Path

import pytest

from travelops_recovery_agent.evaluation.cli import main
from travelops_recovery_agent.evaluation.harness import run_evaluation

FROZEN_TIME = datetime(2026, 8, 14, tzinfo=UTC)


def test_deterministic_benchmark_passes_every_critical_gate() -> None:
    report = run_evaluation(generated_at=FROZEN_TIME)
    assert report.status == "passed"
    assert report.totals.case_count == 22
    assert report.totals.booking_writes_without_valid_approval == 0
    assert report.totals.duplicate_booking_writes == 0
    assert report.totals.unauthorized_execution_attempts == 0
    assert report.totals.model_calls == 0
    assert report.totals.input_tokens == 0
    assert report.totals.cost_usd == 0


def test_semantic_result_hash_is_reproducible() -> None:
    first = run_evaluation(generated_at=FROZEN_TIME)
    second = run_evaluation(generated_at=FROZEN_TIME)
    assert first.semantic_result_hash == second.semantic_result_hash


@pytest.mark.parametrize(
    ("defect", "gate"),
    [
        ("approval_bypass", "booking write bypassed valid approval"),
        ("duplicate_write", "duplicate booking write detected"),
        ("unsafe_tool", "tool selection accuracy below threshold"),
    ],
)
def test_deliberate_safety_defects_fail_critical_gates(defect: str, gate: str) -> None:
    report = run_evaluation(defect=defect, generated_at=FROZEN_TIME)
    assert report.status == "failed"
    assert gate in report.critical_gate_failures


def test_cli_writes_machine_human_and_trace_artifacts(tmp_path: Path) -> None:
    assert main(["validate"]) == 0
    assert main(["run", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "phase-11-evaluation.json").is_file()
    assert (tmp_path / "phase-11-evaluation.md").is_file()
    assert (tmp_path / "phase-11-traces.jsonl").is_file()


def test_cli_exits_nonzero_when_critical_gate_fails(tmp_path: Path) -> None:
    assert (
        main(
            [
                "run",
                "--output-dir",
                str(tmp_path),
                "--inject-defect",
                "approval_bypass",
            ]
        )
        == 2
    )
