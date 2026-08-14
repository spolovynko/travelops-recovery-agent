import { expect, test } from "@playwright/test";

const aggregate = {
  case_count: 19,
  passed_cases: 19,
  task_completion_rate: 1,
  outcome_accuracy: 1,
  correct_tool_selection_rate: 1,
  valid_tool_arguments_rate: 1,
  recommendation_validity_rate: 1,
  evidence_completeness_rate: 0.9474,
  escalation_accuracy: 1,
  approval_integrity_rate: 1,
  booking_writes: 4,
  booking_writes_without_valid_approval: 0,
  duplicate_booking_writes: 0,
  unauthorized_execution_attempts: 0,
  blocked_hostile_requests: 4,
  total_retries: 5,
  latency_total_ms: 1,
  latency_p95_ms: 0.2,
  model_calls: 0,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: 0,
  usage_source: "measured",
};

test("operator reviews keyboard-accessible deterministic release evidence", async ({
  page,
}) => {
  await page.route("**/api/v1/evaluations/phase-12", (route) =>
    route.fulfill({
      json: {
        schema_version: "travelops.context-evaluation-report.v1",
        evaluation_id: "phase12-browser",
        status: "passed",
        generated_at: "2026-08-14T10:00:00Z",
        git_revision: "abc",
        random_seed: 42,
        dataset_version: "phase-12.0.0",
        context_schema_version: "travelops.context.v1",
        context_policy_version: "phase-12.1",
        evaluation_type: "deterministic",
        provider: "recorded_deterministic_fixture",
        model: "none",
        prompt_version: "not_applicable:no_model_calls",
        phase_11_baseline: {
          dataset_version: "phase-11.0.0",
          case_count: 22,
          task_completion_rate: 1,
          outcome_accuracy: 1,
          approval_integrity_rate: 1,
          booking_writes_without_valid_approval: 0,
          duplicate_booking_writes: 0,
          unauthorized_execution_attempts: 0,
        },
        full_context_baseline: {
          case_count: 13,
          passed_cases: 13,
          task_completion_rate: 1,
          outcome_accuracy: 1,
          mandatory_evidence_recall: 1,
          stale_evidence_inclusion: 1,
          unauthorized_evidence_inclusion: 1,
          cross_case_evidence_inclusion: 1,
          correct_tool_exposure_rate: 0.3,
          prohibited_tool_exposure: 5,
          full_context_token_estimate: 22000,
          selective_context_token_estimate: 22000,
          context_reduction_rate: 0,
          selection_latency_total_ms: 0,
          selection_latency_p95_ms: 0,
          cache_hits: 0,
          cache_misses: 0,
          compacted_items: 0,
          approval_integrity_rate: 1,
          booking_writes_without_valid_approval: 0,
          duplicate_booking_writes: 0,
          unauthorized_execution_attempts: 0,
          token_accounting_source: "estimated",
          token_estimate_method: "estimated_characters_div_4",
        },
        selective_context: {
          case_count: 13,
          passed_cases: 13,
          task_completion_rate: 1,
          outcome_accuracy: 1,
          mandatory_evidence_recall: 1,
          stale_evidence_inclusion: 0,
          unauthorized_evidence_inclusion: 0,
          cross_case_evidence_inclusion: 0,
          correct_tool_exposure_rate: 1,
          prohibited_tool_exposure: 0,
          full_context_token_estimate: 22000,
          selective_context_token_estimate: 8500,
          context_reduction_rate: 0.61,
          selection_latency_total_ms: 3,
          selection_latency_p95_ms: 0.4,
          cache_hits: 1,
          cache_misses: 14,
          compacted_items: 2,
          approval_integrity_rate: 1,
          booking_writes_without_valid_approval: 0,
          duplicate_booking_writes: 0,
          unauthorized_execution_attempts: 0,
          token_accounting_source: "estimated",
          token_estimate_method: "estimated_characters_div_4",
        },
        critical_gate_failures: [],
        supported_claims: [],
        unsupported_claims: [],
      },
    }),
  );
  await page.route("**/api/v1/evaluations/phase-11", (route) =>
    route.fulfill({
      json: {
        schema_version: "travelops.evaluation-report.v1",
        evaluation_id: "phase11-browser",
        status: "passed",
        generated_at: "2026-08-14T10:00:00Z",
        semantic_result_hash: "abc",
        contract: {
          system_version: "0.1.0",
          git_revision: "abc",
          configuration: { environment: "test" },
          prompt_version: "not_applicable:no_model_calls",
          model_provider: "recorded_deterministic_fixture",
          model_name: "none",
          dataset_version: "phase-11.0.0",
          random_seed: 42,
          evaluation_type: "deterministic",
          supported_claims: ["Approval integrity is enforced."],
          unsupported_claims: ["Live-model semantic quality."],
        },
        totals: aggregate,
        slices: {
          routine: { ...aggregate, case_count: 3, passed_cases: 3 },
          safety: { ...aggregate, case_count: 12, passed_cases: 12 },
        },
        critical_gate_failures: [],
        cases: [],
      },
    }),
  );

  await page.goto("/evaluations");
  await expect(
    page.getByRole("heading", { name: "Release gates passed" }),
  ).toBeVisible();
  await expect(page.getByText("phase-11.0.0")).toBeVisible();
  await expect(
    page.getByText("No failed cases in this deterministic run."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Full context versus selective context",
    }),
  ).toBeVisible();
  await page.getByRole("region", { name: "Benchmark slice results" }).focus();
  await expect(
    page.getByRole("region", { name: "Benchmark slice results" }),
  ).toBeFocused();
});
