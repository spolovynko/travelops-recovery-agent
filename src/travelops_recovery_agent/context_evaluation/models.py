"""Versioned Phase 12 context experiment contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from travelops_recovery_agent.context_engineering.models import ContextTask


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextScenario(StrEnum):
    LONG_CONVERSATION = "long_conversation"
    REPEATED_TOOL_RESULTS = "repeated_tool_results"
    OVERSIZED_EVIDENCE = "oversized_evidence"
    STALE_EVIDENCE = "stale_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    SUPERSEDED_FACTS = "superseded_facts"
    UNAUTHORIZED_CROSS_CASE = "unauthorized_cross_case"
    CHANGING_PERMISSIONS = "changing_permissions"
    TOOL_OUTPUT_PROMPT_INJECTION = "tool_output_prompt_injection"
    EXCESSIVE_PASSENGER_INFORMATION = "excessive_passenger_information"
    MANDATORY_NEAR_LIMIT = "mandatory_near_limit"
    CACHE_INVALIDATION = "cache_invalidation_after_evidence_change"
    STATE_DEPENDENT_TOOLS = "state_dependent_tools"


class ContextEvaluationCase(Contract):
    case_id: str = Field(pattern=r"^CTX-\d{3}$")
    title: str = Field(min_length=5, max_length=120)
    scenario: ContextScenario
    task: ContextTask
    workflow_node: str
    operator_role: str
    token_budget: int = Field(ge=100, le=20_000)
    expected_selected_evidence: tuple[str, ...]
    mandatory_evidence: tuple[str, ...]
    prohibited_evidence: tuple[str, ...]
    expected_exposed_tools: tuple[str, ...]
    prohibited_tools: tuple[str, ...]
    expected_compaction: bool
    expected_escalation: bool
    expected_final_workflow_outcome: Literal["continue", "safe_escalation"]


class ContextEvaluationDataset(Contract):
    schema_version: Literal["travelops.context-evaluation-dataset.v1"]
    dataset_version: Literal["phase-12.0.0"]
    description: str
    synthetic_data_notice: str
    cases: tuple[ContextEvaluationCase, ...] = Field(min_length=13)

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Phase 12 case IDs must be unique")
        covered = {case.scenario for case in self.cases}
        if covered != set(ContextScenario):
            raise ValueError("Phase 12 dataset must cover every declared scenario")
        return self


class ContextCaseMetrics(Contract):
    passed: bool
    outcome_correct: bool
    mandatory_evidence_recall: float = Field(ge=0, le=1)
    stale_evidence_included: int = Field(ge=0)
    unauthorized_evidence_included: int = Field(ge=0)
    cross_case_evidence_included: int = Field(ge=0)
    tool_exposure_correct: bool
    prohibited_tool_exposure: int = Field(ge=0)
    full_context_token_estimate: int = Field(ge=0)
    selective_context_token_estimate: int = Field(ge=0)
    context_reduction_rate: float
    selection_latency_ms: float = Field(ge=0)
    cache_hits: int = Field(ge=0)
    cache_misses: int = Field(ge=0)
    compacted_items: int = Field(ge=0)
    safe_escalation: bool
    approval_integrity: bool
    booking_writes_without_valid_approval: int = Field(ge=0)
    duplicate_booking_writes: int = Field(ge=0)
    unauthorized_execution_attempts: int = Field(ge=0)


class ContextCaseResult(Contract):
    case_id: str
    scenario: ContextScenario
    expected_selected_evidence: tuple[str, ...]
    actual_selected_evidence: tuple[str, ...]
    expected_exposed_tools: tuple[str, ...]
    actual_exposed_tools: tuple[str, ...]
    final_workflow_outcome: Literal["continue", "safe_escalation"]
    metrics: ContextCaseMetrics
    safe_diagnostics: tuple[str, ...]


class ContextAggregate(Contract):
    case_count: int
    passed_cases: int
    task_completion_rate: float
    outcome_accuracy: float
    mandatory_evidence_recall: float
    stale_evidence_inclusion: int
    unauthorized_evidence_inclusion: int
    cross_case_evidence_inclusion: int
    correct_tool_exposure_rate: float
    prohibited_tool_exposure: int
    full_context_token_estimate: int
    selective_context_token_estimate: int
    context_reduction_rate: float
    selection_latency_total_ms: float
    selection_latency_p95_ms: float
    cache_hits: int
    cache_misses: int
    compacted_items: int
    approval_integrity_rate: float
    booking_writes_without_valid_approval: int
    duplicate_booking_writes: int
    unauthorized_execution_attempts: int
    token_accounting_source: Literal["estimated"] = "estimated"
    token_estimate_method: Literal["estimated_characters_div_4"] = (
        "estimated_characters_div_4"
    )


class Phase11Comparison(Contract):
    dataset_version: str
    case_count: int
    task_completion_rate: float
    outcome_accuracy: float
    approval_integrity_rate: float
    booking_writes_without_valid_approval: int
    duplicate_booking_writes: int
    unauthorized_execution_attempts: int


class ContextEvaluationReport(Contract):
    schema_version: Literal["travelops.context-evaluation-report.v1"]
    evaluation_id: str
    status: Literal["passed", "failed"]
    generated_at: datetime
    git_revision: str
    random_seed: int
    dataset_version: str
    context_schema_version: str
    context_policy_version: str
    evaluation_type: Literal["deterministic"] = "deterministic"
    provider: Literal["recorded_deterministic_fixture"] = (
        "recorded_deterministic_fixture"
    )
    model: Literal["none"] = "none"
    prompt_version: Literal["not_applicable:no_model_calls"] = (
        "not_applicable:no_model_calls"
    )
    phase_11_baseline: Phase11Comparison
    full_context_baseline: ContextAggregate
    selective_context: ContextAggregate
    critical_gate_failures: tuple[str, ...]
    cases: tuple[ContextCaseResult, ...]
    supported_claims: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
