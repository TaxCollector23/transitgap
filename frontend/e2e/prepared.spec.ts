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
  await page.getByRole("button", { name: "Which stops are harder to reach by wheelchair?" }).click();
  await expect(page.locator(".gap-ranking li")).toHaveCount(10);
  await page.locator(".gap-ranking button").first().click();
  await expect(page.locator(".study-detail")).toContainText("Standard network");
  await page.getByRole("button", { name: "Prepare a letter" }).click();
  await expect(page.getByLabel("Review and edit before sending")).toHaveValue(
    /Please assess pedestrian access/,
  );
});
