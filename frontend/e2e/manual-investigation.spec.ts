import { expect, test } from "@playwright/test";
import {
  queuePayload,
  searchPayload,
  validationPayload,
  workspacePayload,
} from "../src/test/fixtures";

test("operator opens, investigates, searches, validates and refreshes a case URL", async ({
  page,
}) => {
  let workspaceLoads = 0;
  await page.route("**/api/v1/recovery-cases", (route) =>
    route.fulfill({ json: queuePayload }),
  );
  await page.route("**/api/v1/recovery-cases/CASE-0001", (route) => {
    workspaceLoads += 1;
    return route.fulfill({ json: workspacePayload });
  });
  await page.route("**/api/v1/alternative-itineraries/search", (route) =>
    route.fulfill({ json: searchPayload }),
  );
  await page.route("**/api/v1/itineraries/validate", (route) =>
    route.fulfill({ json: validationPayload }),
  );

  await page.goto("/cases");
  await page.getByRole("link", { name: /investigate case/i }).click();
  await expect(page).toHaveURL(/\/cases\/CASE-0001$/);
  await expect(page.getByText("Mina Vale")).toBeVisible();
  await expect(page.getByText("Synthetic standard recovery")).toBeVisible();
  await page.getByRole("button", { name: "Search alternatives" }).click();
  await expect(page.getByText("Option 1")).toBeVisible();
  await page.getByRole("button", { name: "Validate candidate" }).click();
  await expect(page.getByText("Structural checks passed")).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/cases\/CASE-0001$/);
  await expect(page.getByText("Mina Vale")).toBeVisible();
  expect(workspaceLoads).toBeGreaterThan(1);
});
