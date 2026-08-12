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
    screen.getByText(/Seat inventory and ticket rules: not evaluated/i),
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
