import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
const password = readFileSync(new URL("../../.env", import.meta.url), "utf8")
  .match(/^WATCH_ADMIN_PASSWORD=(.+)$/m)?.[1]
  .trim();

test("system appearance, persistence, storage sync and blocked storage", async ({
  page,
  context,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByLabel("Appearance")).toHaveValue("system");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Appearance").selectOption("dark");
  await page.reload();
  await expect(page.getByLabel("Appearance")).toHaveValue("dark");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");
  const second = await context.newPage();
  await second.goto("/");
  await second.getByLabel("Appearance").selectOption("light");
  await expect(page.getByLabel("Appearance")).toHaveValue("light");
  await second.close();
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("Storage disabled");
      },
    });
  });
  await page.reload();
  await page.getByLabel("Appearance").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeEnabled();
});

test("dark workspace, map overlays, dialogs, narrow layout and contrast", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Appearance").selectOption("dark");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Situational overview" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Place a site on map" }),
  ).toBeEnabled({ timeout: 30000 });
  await page
    .getByRole("checkbox", { name: "Satellite hotspots", exact: true })
    .uncheck();
  await page.getByRole("slider", { name: "Opacity" }).fill("0.5");
  await page.getByLabel("Appearance").selectOption("light");
  await expect(
    page.getByRole("button", { name: "Place a site on map" }),
  ).toBeEnabled({ timeout: 30000 });
  await page.getByLabel("Appearance").selectOption("dark");
  await expect(
    page.getByRole("button", { name: "Place a site on map" }),
  ).toBeEnabled({ timeout: 30000 });
  await expect(
    page.getByRole("checkbox", { name: "Satellite hotspots", exact: true }),
  ).not.toBeChecked();
  await expect(page.getByRole("slider", { name: "Opacity" })).toHaveValue(
    "0.5",
  );
  await expect(page.locator(".panel").first()).toHaveCSS(
    "background-color",
    "rgb(25, 42, 57)",
  );
  await page.screenshot({
    path: "/tmp/osint-dark-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Add asset", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCSS(
    "background-color",
    "rgb(25, 42, 57)",
  );
  await page.getByLabel("Asset name").fill("Unsaved dark theme draft");
  expect(
    (await new AxeBuilder({ page }).include("dialog").analyze()).violations,
  ).toEqual([]);
  // OS theme updates must not discard the open form's draft.
  await page.evaluate(() =>
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "osint-watch-theme",
        newValue: "light",
      }),
    ),
  );
  await expect(page.getByLabel("Asset name")).toHaveValue(
    "Unsaved dark theme draft",
  );
  await expect(page.getByRole("dialog")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await page.evaluate(() =>
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "osint-watch-theme",
        newValue: "dark",
      }),
    ),
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("dialog", { name: "Discard changes", exact: true })
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await page.getByRole("button", { name: "Saved assets", exact: true }).click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Appearance")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "/tmp/osint-dark-mobile.png", fullPage: true });
  await page.getByLabel("Appearance").selectOption("light");
  await expect(page.locator(".panel").first()).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
});
