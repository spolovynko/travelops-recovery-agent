import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import { EvaluationSummaryPage } from "./EvaluationSummaryPage";

const aggregate = {
  case_count: 19,
  passed_cases: 19,
  task_completion_rate: 1,
  outcome_accuracy: 1,
  correct_tool_selection_rate: 1,
  valid_tool_arguments_rate: 1,
  recommendation_validity_rate: 1,
  evidence_completeness_rate: 0.95,
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

const report = {
  schema_version: "travelops.evaluation-report.v1",
  evaluation_id: "phase11-example",
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
    supported_claims: ["Approval is required."],
    unsupported_claims: ["Live-model quality."],
  },
  totals: aggregate,
  slices: { safety: { ...aggregate, case_count: 12, passed_cases: 12 } },
  critical_gate_failures: [],
  cases: [
    {
      case_id: "EVAL-001",
      slices: ["safety"],
      expected_outcome: "recovered",
      actual_outcome: "recovered",
      passed: true,
      safe_diagnostics: ["outcome=recovered"],
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("evaluation summary", () => {
  it("announces status and renders safety metrics without raw prompts", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(report), { status: 200 }),
        ),
    );
    render(
      <QueryClientProvider client={createQueryClient(false)}>
        <MemoryRouter>
          <EvaluationSummaryPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading evaluation report",
    );
    expect(
      await screen.findByRole("heading", { name: "Release gates passed" }),
    ).toBeVisible();
    expect(
      screen.getByText("Unapproved writes").parentElement,
    ).toHaveTextContent("0");
    expect(
      screen.getByRole("region", { name: "Benchmark slice results" }),
    ).toHaveAttribute("tabindex", "0");
    expect(screen.queryByText(/raw prompt/i)).not.toBeInTheDocument();
  });
});
