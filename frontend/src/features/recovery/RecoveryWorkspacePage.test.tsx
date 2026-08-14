import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import {
  searchPayload,
  validationPayload,
  workspacePayload,
} from "../../test/fixtures";
import { RecoveryWorkspacePage } from "./RecoveryWorkspacePage";

function renderPage(path = "/cases/CASE-0001") {
  return render(
    <QueryClientProvider client={createQueryClient(false)}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:caseId" element={<RecoveryWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("renders minimized investigation, evidence, policy and itinerary facts", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(workspacePayload), { status: 200 }),
      ),
  );
  renderPage();
  expect(
    await screen.findByRole("heading", { name: "Investigation" }),
  ).toBeVisible();
  expect(screen.getByText("Mina Vale")).toBeVisible();
  expect(screen.getByText("NV 101")).toBeVisible();
  expect(screen.getByText("30 minute delay")).toBeVisible();
  expect(screen.getByText("Synthetic standard recovery")).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Recommended itinerary" }),
  ).toBeVisible();
  expect(screen.getByText("REC-FLT-NV1003")).toBeVisible();
  expect(screen.getByText("Supporting evidence")).toBeVisible();
  expect(screen.getByText("Rejected options and reasons (1)")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeEnabled();
});

it("renders proposal approval controls separately from execution", async () => {
  const option = workspacePayload.recommendation.recommended_itinerary;
  const proposalPayload = {
    proposal: {
      proposal_id: "proposal-1",
      version: 1,
      case_id: "CASE-0001",
      booking_id: "BKG-0001",
      recommendation_reference: "recommendation:abc",
      validation_reference: "validation:abc",
      proposed_itinerary: option,
      itinerary_fingerprint: "a".repeat(64),
      evidence_snapshot: option?.evidence_references ?? [],
      evidence_completeness: "complete",
      evidence_fingerprint: "b".repeat(64),
      created_at: "2026-08-14T10:00:00Z",
      expires_at: "2026-08-14T10:30:00Z",
      created_by: "proposal-preparer",
      status: "awaiting_approval",
      required_approver: {
        required_role: "recovery_operator",
        self_approval_prohibited: true,
      },
      decision: null,
      execution_eligible: false,
      revalidation: {
        status: "not_run",
        checked_at: null,
        checks: [],
        failure_reasons: [],
      },
      execution_result: null,
      failure_reasons: [],
      escalation_reasons: [],
      workflow_run_id: null,
      correlation_id: "corr-1",
    },
    audit_history: [
      {
        audit_id: "audit-1",
        sequence: 1,
        proposal_id: "proposal-1",
        event_type: "proposal.created",
        actor_id: "proposal-preparer",
        occurred_at: "2026-08-14T10:00:00Z",
        correlation_id: "corr-1",
        details: {},
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation((input: RequestInfo | URL) =>
        Promise.resolve(
          new Response(
            JSON.stringify(
              String(input).includes("proposal")
                ? proposalPayload
                : workspacePayload,
            ),
            { status: 200 },
          ),
        ),
      ),
  );
  renderPage();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Prepare proposal" }),
  );
  expect(
    await screen.findByRole("button", { name: "Approve exact proposal" }),
  ).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "Revalidate and execute" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Immutable audit history (1)")).toBeVisible();
});

it("renders a clear escalation when recommendation evidence is insufficient", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...workspacePayload,
          recommendation: {
            case_id: "CASE-0001",
            outcome: "insufficient_evidence",
            recommended_itinerary: null,
            other_validated_options: [],
            option_results: [],
            evidence_references: [],
            evidence_completeness: "insufficient",
            escalation_reason:
              "Seat evidence is missing for the candidate flights.",
            ranking_method: "stable ranking",
          },
        }),
        { status: 200 },
      ),
    ),
  );
  renderPage();
  expect(
    await screen.findByRole("heading", { name: "Evidence is insufficient" }),
  ).toBeVisible();
  expect(screen.getByText(/Seat evidence is missing/)).toBeVisible();
});

it("searches alternatives and shows passed, failed, not-evaluated and deferred validation", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify(workspacePayload), { status: 200 }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(searchPayload), { status: 200 }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(validationPayload), { status: 200 }),
    );
  vi.stubGlobal("fetch", fetchMock);
  renderPage();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Search alternatives" }),
  );
  expect(await screen.findByText("Option 1")).toBeVisible();
  expect(
    screen.getByText(
      /Seat inventory and ticket rules: not evaluated by this manual explorer/i,
    ),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Validate candidate" }));
  expect(await screen.findByText("Structural checks passed")).toBeVisible();
  for (const status of ["passed", "failed", "not evaluated", "deferred"])
    expect(screen.getAllByText(status)[0]).toBeVisible();
});

it("shows a safe not-found page for an unknown URL case", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "not_found",
            message: "Recovery case CASE-9999 was not found.",
            retryable: false,
          },
        }),
        { status: 404 },
      ),
    ),
  );
  renderPage("/cases/CASE-9999");
  expect(
    await screen.findByRole("heading", {
      name: /case CASE-9999 is unavailable/i,
    }),
  ).toBeVisible();
});

it("shows a safe error when candidate validation fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(workspacePayload), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(searchPayload), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "service_unavailable",
              message: "Recovery data is temporarily unavailable.",
              retryable: true,
            },
          }),
          { status: 503 },
        ),
      ),
  );
  renderPage();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Search alternatives" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Validate candidate" }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Recovery data is temporarily unavailable.",
  );
});
