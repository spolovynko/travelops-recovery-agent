import { expect, test } from "@playwright/test";
import { workflowPayload, workspacePayload } from "../src/test/fixtures";

test("durable workflow reconnects after a backend stream restart and survives refresh", async ({
  page,
}) => {
  let streamConnections = 0;
  let completed = false;
  await page.route("**/api/v1/recovery-cases/CASE-0001", (route) =>
    route.fulfill({ json: workspacePayload }),
  );
  await page.route(
    `**/api/v1/workflow-runs/${workflowPayload.run_id}`,
    (route) =>
      route.fulfill({
        json: completed
          ? workflowPayload
          : {
              ...workflowPayload,
              status: "running",
              current_node: "tool_execution",
              finished_at: null,
              outcome_summary: null,
              last_event_sequence: 12,
            },
      }),
  );
  await page.route(
    `**/api/v1/workflow-runs/${workflowPayload.run_id}/events**`,
    async (route) => {
      streamConnections += 1;
      if (streamConnections === 1) {
        await route.abort("connectionfailed");
        return;
      }
      completed = true;
      await route.fulfill({
        contentType: "text/event-stream",
        body:
          `id: ${workflowPayload.run_id}:26\n` +
          "event: workflow.completed\n" +
          `data: ${JSON.stringify({
            event_id: `${workflowPayload.run_id}:26`,
            run_id: workflowPayload.run_id,
            sequence: 26,
            type: "workflow.completed",
            occurred_at: workflowPayload.finished_at,
            payload: { status: "completed" },
          })}\n\n`,
      });
    },
  );

  await page.goto(
    `/cases/CASE-0001?run=${encodeURIComponent(workflowPayload.run_id)}`,
  );
  await expect(
    page.getByText("Reconnecting; durable state retained"),
  ).toBeVisible();
  await expect(page.getByText(/Final state · run-/)).toBeVisible({
    timeout: 10_000,
  });
  expect(streamConnections).toBeGreaterThanOrEqual(2);

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`run=${workflowPayload.run_id}`));
  await expect(page.getByText(/Final state · run-/)).toBeVisible();
  await expect(
    page.getByText("The read-only investigation is complete."),
  ).toBeVisible();
});
