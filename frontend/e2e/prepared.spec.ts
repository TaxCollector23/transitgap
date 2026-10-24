import { test, expect } from "@playwright/test";
test("prepared production views work while the route engine is unavailable", async ({
  page,
}) => {
  await page.route("**/*", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (
      ["/health", "/health/live", "/routing/initialize", "/coverage", "/stops", "/gaps"].includes(path) ||
      path.startsWith("/stops/") ||
      path.startsWith("/letters/")
    )
      return route.abort();
    return route.continue();
  });
  await page.goto(process.env.TRANSITGAP_E2E_URL || "http://127.0.0.1:4173/");
  await expect(page.locator(".landing-art")).toBeVisible({
    timeout: 8000,
  });
  await page.getByRole("link", { name: "Open the map", exact: true }).first().click();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({ timeout: 8000 });
  await page
    .getByRole("button", { name: "Try an example trip near Diridon Station" })
    .click();
  await expect(page.locator(".field-value").nth(1)).toContainText("Bay 11");
  await page.getByRole("button", { name: "For cities and advocates" }).click();
  await expect(page.getByRole("heading", { name: "Which stops are harder to reach by wheelchair?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download as CSV" })).toBeVisible();
  await expect(page.locator(".advocate-overview")).toContainText(/of \d+ stops in the Diridon pilot/, { timeout: 30_000 });
  await expect(page.locator(".gap-ranking li")).toHaveCount(10);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download as CSV" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("transitgap-wheelchair-reachability-sample.csv");
  await page.locator(".gap-ranking button").first().click();
  await expect(page.locator(".study-detail")).toContainText("Standard network");
  await page.getByRole("button", { name: "Prepare a letter" }).click();
  await expect(page.getByLabel("Review and edit before sending")).toHaveValue(
    /Please assess pedestrian access/,
  );
});

test("the CA-17 example starts at the district view and reaches Milpitas BART", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(process.env.TRANSITGAP_E2E_URL || "http://127.0.0.1:4173/");
  await expect(page.locator(".landing-art")).toBeVisible({ timeout: 8000 });
  await page.getByRole("link", { name: "Open the map", exact: true }).first().click();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({ timeout: 8000 });
  await page.getByRole("button", { name: "Try an example trip to Milpitas BART" }).click();
  await expect(page.locator(".field-value").first()).toContainText("Milpitas BART");
  await expect(page.locator(".field-value").nth(1)).toContainText("Milpitas");
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(page.locator(".route-result")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".route-limitations")).toContainText(/Map data shows.*stairs/i);
  await expect(page.locator(".route-limitations")).toContainText(/no walking-path data/i);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
