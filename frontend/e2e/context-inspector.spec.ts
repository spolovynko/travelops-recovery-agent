import { expect, test } from "@playwright/test";

test("developer inspects evidence reasons, budget, and governed tools", async ({
  page,
}) => {
  await page.route("**/api/v1/developer/context-inspector?**", (route) =>
    route.fulfill({
      json: {
        schema_version: "travelops.context.v1",
        policy_version: "phase-12.1",
        build_id: "context-browser",
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
            content: "Operator case scope was revalidated.",
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
            detail: "Untrusted tool output was rejected.",
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
          key_reference: "ctx-browser",
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
      },
    }),
  );

  await page.goto("/developer/context");
  await expect(
    page.getByRole("heading", { name: "Context ready" }),
  ).toBeVisible();
  await expect(page.getByText("1800 est. tokens")).toBeVisible();
  await expect(page.getByText("untrusted evidence")).toBeVisible();
  await expect(page.getByText("execute_rebooking")).toBeVisible();
  const region = page.getByRole("region", {
    name: "Context evidence inclusion and exclusion reasons",
  });
  await region.focus();
  await expect(region).toBeFocused();
});
