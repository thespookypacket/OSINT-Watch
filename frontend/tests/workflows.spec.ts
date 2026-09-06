import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const env = readFileSync(new URL("../../.env", import.meta.url), "utf8");
const password = env.match(/^WATCH_ADMIN_PASSWORD=(.+)$/m)?.[1].trim();
const ids: string[] = [];
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Situational overview" }),
  ).toBeVisible();
});
test.afterEach(async ({ page }) => {
  const list = await page.request.get("/api/v1/assets?limit=1000");
  if (list.ok())
    for (const a of (await list.json()).items) {
      if (ids.includes(a.id) || a.name.startsWith("E2E Workflow"))
        await page.request.delete("/api/v1/assets/" + a.id, {
          headers: { Origin: "http://localhost:8080" },
        });
    }
});
test("asset import failure, create, edit, delete and mobile layout", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Saved assets", exact: true }).click();
  await page
    .getByRole("button", { name: "Import assets", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Import assets" });
  await dialog
    .getByLabel("Or paste file contents")
    .fill(
      "name,longitude,latitude\nE2E Workflow Import,-105,40\nInvalid,999,40",
    );
  await dialog
    .getByRole("button", { name: "Import assets", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("no assets saved");
  await dialog
    .getByLabel("Or paste file contents")
    .fill("name,longitude,latitude\nE2E Workflow Import,-105,40");
  await dialog
    .getByRole("button", { name: "Import assets", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("cell", { name: "E2E Workflow Import", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit E2E Workflow Import", exact: true })
    .click();
  await page.getByLabel("Asset name").fill("E2E Workflow Edited");
  await page.getByRole("button", { name: "Save asset", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "E2E Workflow Edited", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Delete E2E Workflow Edited", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Delete asset" })
    .getByRole("button", { name: "Delete asset", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "E2E Workflow Edited", exact: true }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Saved assets" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "/tmp/osint-mobile.png", fullPage: true });
});
test("map overlays, event evidence, exposure and acknowledgment", async ({
  page,
}) => {
  await page.getByRole("combobox", { name: "Time window" }).selectOption("all");
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  expect(
    (await page.locator(".map-canvas").boundingBox())!.height,
  ).toBeGreaterThan(300);
  await page
    .getByRole("checkbox", { name: "Satellite hotspots", exact: true })
    .uncheck();
  await expect(
    page.getByRole("checkbox", { name: "Satellite hotspots", exact: true }),
  ).not.toBeChecked();
  await page
    .getByRole("checkbox", { name: "Satellite hotspots", exact: true })
    .check();
  await page.getByRole("slider", { name: "Opacity" }).fill("0.5");
  await page.getByRole("button", { name: "Map layers −", exact: true }).click();
  await page.getByRole("button", { name: "Place a site on map" }).click();
  await page
    .locator(".maplibregl-canvas")
    .click({ position: { x: 300, y: 230 } });
  await expect(page.getByRole("dialog", { name: "Add asset" })).toBeVisible();
  await page.getByLabel("Asset name").fill("E2E Workflow Map Site");
  await page.getByRole("button", { name: "Save asset", exact: true }).click();
  await page.locator(".event-table tbody .event-link").first().click();
  await expect(
    page.getByRole("heading", { name: "Revision history" }),
  ).toBeVisible();
  // Use an actual retained point event to exercise exposure without inventing source reports.
  const response = await page.request.get("/api/v1/events?limit=1000");
  const event = (await response.json()).features.find(
    (f: { geometry?: { type: string } }) => f.geometry?.type === "Point",
  );
  expect(event).toBeTruthy();
  const created = await page.request.post("/api/v1/assets", {
    headers: { Origin: "http://localhost:8080" },
    data: {
      name: "E2E Workflow Exposed",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [
              event.geometry.coordinates[0] - 0.001,
              event.geometry.coordinates[1] - 0.001,
            ],
            [
              event.geometry.coordinates[0] + 0.001,
              event.geometry.coordinates[1] - 0.001,
            ],
            [
              event.geometry.coordinates[0] + 0.001,
              event.geometry.coordinates[1] + 0.001,
            ],
            [
              event.geometry.coordinates[0] - 0.001,
              event.geometry.coordinates[1] + 0.001,
            ],
            [
              event.geometry.coordinates[0] - 0.001,
              event.geometry.coordinates[1] - 0.001,
            ],
          ],
        ],
      },
      min_severity: 0,
      radius_km: 0,
    },
  });
  expect(created.ok()).toBeTruthy();
  ids.push((await created.json()).id);
  await page.getByRole("button", { name: "Refresh dashboard" }).click();
  await page.getByRole("button", { name: "Alerts", exact: true }).click();
  const row = page
    .getByRole("row")
    .filter({ hasText: "E2E Workflow Exposed" })
    .first();
  await expect(row).toContainText("intersects E2E Workflow Exposed");
  await row.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(row).toContainText("acknowledged");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Place a site on map" }),
  ).toBeEnabled();
  await page.screenshot({ path: "/tmp/osint-desktop.png", fullPage: true });
});
test("source freshness and optional services stay explicit", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "NASA FIRMS", exact: false }).first(),
  ).toBeVisible();
  await expect(page.getByText("key required", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByText("Not connected", { exact: false }).first(),
  ).toBeVisible();
});

test("draw an area with undo and import GeoJSON boundaries", async ({
  page,
}) => {
  await expect(page.getByRole("button", { name: "Draw an area" })).toBeEnabled({
    timeout: 20000,
  });
  await page.getByRole("button", { name: "Map layers −", exact: true }).click();
  await page.getByRole("button", { name: "Draw an area", exact: true }).click();
  const canvas = page.locator(".maplibregl-canvas");
  await canvas.click({ position: { x: 250, y: 180 } });
  await canvas.click({ position: { x: 350, y: 180 } });
  await canvas.click({ position: { x: 350, y: 280 } });
  await page.getByRole("button", { name: "Undo last point" }).click();
  await expect(
    page.getByRole("button", { name: "Finish area (2)" }),
  ).toBeDisabled();
  await canvas.click({ position: { x: 350, y: 280 } });
  await page.getByRole("button", { name: "Finish area (3)" }).click();
  await page.getByLabel("Asset name").fill("E2E Workflow Drawn Area");
  await page.getByRole("button", { name: "Save asset", exact: true }).click();
  await page.getByRole("button", { name: "Saved assets", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "E2E Workflow Drawn Area" }),
  ).toContainText("Area");
  await page
    .getByRole("button", { name: "Import assets", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Import assets" });
  await modal.getByRole("combobox", { name: "Format" }).selectOption("geojson");
  await modal.getByLabel("Or paste file contents").fill(
    JSON.stringify({
      type: "Feature",
      properties: { name: "E2E Workflow Imported Area" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-105, 40],
            [-104.9, 40],
            [-104.9, 40.1],
            [-105, 40],
          ],
        ],
      },
    }),
  );
  await modal
    .getByRole("button", { name: "Import assets", exact: true })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: "E2E Workflow Imported Area" }),
  ).toContainText("Area");
});

test("NetBox setup, queued sync and failure recovery", async ({ page }) => {
  await page.getByRole("button", { name: "Saved assets", exact: true }).click();
  const panel = page.getByRole("region", {
    name: "NetBox site synchronization",
  });
  await expect(
    panel.getByRole("button", { name: "Sync from NetBox" }),
  ).toBeDisabled();
  await expect(panel).toContainText("WATCH_NETBOX_URL");
  let queued = false;
  let completed = false;
  await page.route("**/api/v1/integrations/netbox", async (route) => {
    await route.fulfill({
      json: {
        configured: true,
        interval_seconds: 3600,
        last_success: completed ? new Date().toISOString() : null,
        last_error: null,
        result: completed
          ? { created: 2, updated: 0, unlocated: 1, missing: 0 }
          : null,
        job: queued
          ? {
              id: "test-sync",
              status: completed ? "done" : "pending",
              error: null,
            }
          : null,
      },
    });
  });
  await page.route("**/api/v1/integrations/netbox/sync", async (route) => {
    queued = true;
    await route.fulfill({ status: 202, json: { id: "test-sync" } });
  });
  await expect(
    panel.getByRole("button", { name: "Sync from NetBox" }),
  ).toBeEnabled({ timeout: 10000 });
  await panel.getByRole("button", { name: "Sync from NetBox" }).click();
  await expect(
    panel.getByRole("button", { name: "Sync queued or running" }),
  ).toBeDisabled();
  completed = true;
  await expect(panel).toContainText("2 added", { timeout: 10000 });
  await expect(
    panel.getByRole("button", { name: "Sync from NetBox" }),
  ).toBeEnabled();
  await page.route("**/api/v1/integrations/netbox/sync", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "Sync temporarily unavailable" } },
    }),
  );
  await panel.getByRole("button", { name: "Sync from NetBox" }).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Sync from NetBox" }),
  ).toBeEnabled();
});
