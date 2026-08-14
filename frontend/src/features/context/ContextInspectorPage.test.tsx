import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import { ContextInspectorPage } from "./ContextInspectorPage";

const report = {
  schema_version: "travelops.context.v1",
  policy_version: "phase-12.1",
  build_id: "context-example",
  status: "ready",
  case_id: "CASE-0002",
  task: "investigate",
  workflow_node: "model_reasoning",
  selected: [
    {
      evidence_id: "AUTH-CASE-0002",
      source_type: "business_fact",
      authority: 4,
      freshness: "current",
      sensitivity: "internal",
      content: "Operator scope was revalidated.",
      original_token_estimate: 10,
      selected_token_estimate: 10,
      compacted: false,
      durable_fact_ids: ["fact:auth"],
      conflicts_with: [],
      supersedes: [],
    },
  ],
  decisions: [
    {
      evidence_id: "AUTH-CASE-0002",
      disposition: "included",
      reason: "mandatory_evidence",
      mandatory: true,
      token_estimate: 10,
      detail: "Selected safely.",
    },
    {
      evidence_id: "INJECTION-CASE-0002",
      disposition: "rejected",
      reason: "untrusted_evidence",
      mandatory: false,
      token_estimate: 20,
      detail: "Untrusted content was rejected.",
    },
  ],
  token_accounting: {
    budget: 1800,
    selected_estimate: 10,
    tool_schema_estimate: 500,
    remaining_estimate: 1290,
    estimate_method: "estimated_characters_div_4",
    provider_exact: false,
  },
  mandatory_evidence_coverage: 1,
  stale_rejection_count: 0,
  unauthorized_rejection_count: 0,
  cross_case_rejection_count: 0,
  conflict_count: 0,
  compacted_count: 0,
  excluded_count: 1,
  cache: {
    hit: false,
    key_reference: "ctx-example",
    cache_version: "phase-12.1",
  },
  selection_latency_ms: 0.4,
  tools: [
    {
      name: "get_booking",
      kind: "read",
      exposed: true,
      reason: "minimum_required_for_step",
      token_estimate: 100,
      input_schema: {},
    },
    {
      name: "execute_rebooking",
      kind: "write",
      exposed: false,
      reason: "task_not_allowed",
      token_estimate: 0,
      input_schema: null,
    },
  ],
  summary_provenance: [],
  escalation_reason: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("context inspector", () => {
  it("renders budget, evidence reasons, and governed tools as safe text", async () => {
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
          <ContextInspectorPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Context ready" }),
    ).toBeVisible();
    expect(screen.getByText("Total budget").parentElement).toHaveTextContent(
      "1800 est. tokens",
    );
    expect(
      screen.getByRole("region", {
        name: "Context evidence inclusion and exclusion reasons",
      }),
    ).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("untrusted evidence")).toBeVisible();
    expect(screen.getByText("execute_rebooking")).toBeVisible();

    await userEvent.selectOptions(
      screen.getByLabelText("Operator role"),
      "viewer",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Inspect context" }),
    );
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
