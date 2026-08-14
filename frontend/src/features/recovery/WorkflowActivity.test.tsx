import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import { workflowPayload, workspacePayload } from "../../test/fixtures";
import { RecoveryWorkspacePage } from "./RecoveryWorkspacePage";

class EventSourceMock {
  static instances: EventSourceMock[] = [];
  readonly url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(url: string | URL) {
    this.url = url.toString();
    EventSourceMock.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const callback = listener as (event: Event) => void;
    const callbacks = this.listeners.get(type) ?? new Set();
    callbacks.add(callback);
    this.listeners.set(type, callbacks);
  }

  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ) {
    this.listeners.get(type)?.delete(listener as (event: Event) => void);
  }

  close() {}

  emit(type: string, data: object) {
    const event = new MessageEvent("message", { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

function renderRun(status: "running" | "completed" = "completed") {
  const workflow = {
    ...workflowPayload,
    status,
    current_node: status === "running" ? "tool_execution" : null,
    finished_at: status === "completed" ? workflowPayload.finished_at : null,
  };
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(workspacePayload), { status: 200 }),
      )
      .mockResolvedValue(
        new Response(JSON.stringify(workflow), { status: 200 }),
      ),
  );
  return render(
    <QueryClientProvider client={createQueryClient(false)}>
      <MemoryRouter
        initialEntries={[`/cases/CASE-0001?run=${workflowPayload.run_id}`]}
      >
        <Routes>
          <Route path="/cases/:caseId" element={<RecoveryWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  EventSourceMock.instances = [];
  vi.unstubAllGlobals();
});

it("restores completed steps, safe tools, evidence and outcome from the run URL", async () => {
  renderRun();

  expect(
    await screen.findByText("Final state · run-0123456789abcdef"),
  ).toBeVisible();
  expect(screen.getByText("get booking · completed")).toBeVisible();
  expect(
    screen.getByText("The read-only investigation is complete."),
  ).toBeVisible();
  expect(
    screen.getAllByText("Evidence")[1]?.nextElementSibling,
  ).toHaveTextContent("1");
});

it("connects from the snapshot cursor and reports reconnect without losing state", async () => {
  vi.stubGlobal("EventSource", EventSourceMock);
  renderRun("running");

  expect(await screen.findByText("Connecting to live progress")).toBeVisible();
  const source = EventSourceMock.instances[0];
  expect(source.url).toContain("cursor=26");
  act(() => source.onopen?.());
  expect(screen.getByText("Live progress connected")).toBeVisible();
  act(() => source.onerror?.());
  expect(
    screen.getByText("Reconnecting; durable state retained"),
  ).toBeVisible();
});
