import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import { queuePayload } from "../../test/fixtures";
import { CaseQueuePage } from "./CaseQueuePage";

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient(false)}>
      <MemoryRouter>
        <CaseQueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("case queue", () => {
  it("shows loading and then deterministic queue facts", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(queuePayload), { status: 200 }),
        ),
    );
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading disruption queue",
    );
    expect(
      await screen.findByText("Short delay on originating flight"),
    ).toBeVisible();
    expect(screen.getByText("ZRA")).toBeVisible();
    expect(screen.getByText("delayed")).toBeVisible();
  });

  it("shows a useful empty state", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ cases: [] }), { status: 200 }),
        ),
    );
    renderPage();
    expect(await screen.findByText("No disruption cases")).toBeVisible();
  });

  it("shows safe errors and supports keyboard navigation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
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
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "temporarily unavailable",
    );

    cleanup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(queuePayload), { status: 200 }),
        ),
    );
    renderPage();
    const user = userEvent.setup();
    const link = await screen.findByRole("link", { name: /investigate case/i });
    await user.tab();
    expect(document.activeElement).toBe(link);
  });
});
