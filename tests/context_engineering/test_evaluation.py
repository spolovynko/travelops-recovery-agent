"""Phase 12 dataset, gates, and seeded-defect tests."""

from travelops_recovery_agent.context_evaluation.harness import (
    load_dataset,
    run_context_evaluation,
)


def test_phase_12_dataset_and_deterministic_experiment_pass() -> None:
    dataset = load_dataset()
    report = run_context_evaluation()

    assert len(dataset.cases) == 13
    assert report.status == "passed"
    assert report.selective_context.mandatory_evidence_recall == 1
    assert report.selective_context.stale_evidence_inclusion == 0
    assert report.selective_context.unauthorized_evidence_inclusion == 0
    assert report.selective_context.cross_case_evidence_inclusion == 0
    assert report.selective_context.prohibited_tool_exposure == 0
    assert report.selective_context.context_reduction_rate > 0
    assert report.phase_11_baseline.task_completion_rate == 1


def test_deliberate_phase_12_defects_fail_the_matching_regression_gate() -> None:
    cross_case = run_context_evaluation(defect="cross_case_cache")
    write_tool = run_context_evaluation(defect="write_tool_leak")
    mandatory = run_context_evaluation(defect="mandatory_drop")

    assert cross_case.status == "failed"
    assert (
        "cross-case evidence entered selective context"
        in cross_case.critical_gate_failures
    )
    assert write_tool.status == "failed"
    assert "a prohibited tool was exposed" in write_tool.critical_gate_failures
    assert mandatory.status == "failed"
    assert "mandatory evidence recall below 100%" in mandatory.critical_gate_failures
