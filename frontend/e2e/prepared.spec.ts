import { test, expect } from "@playwright/test";
test("prepared production views work while the route engine is unavailable", async ({
  page,
}) => {
  await page.route("**/*", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (
      ["/health", "/coverage", "/stops", "/gaps"].includes(path) ||
      path.startsWith("/stops/") ||
      path.startsWith("/letters/")
    )
      return route.abort();
    return route.continue();
  });
  await page.goto("http://127.0.0.1:4173/");
  await expect(page.locator(".network-preview svg")).toBeVisible({
    timeout: 8000,
  });
  await page.getByRole("link", { name: "Open the map" }).click();
  await expect(page.locator(".dataset-status.is-ready")).toContainText(
    "3,348",
    { timeout: 8000 },
  );
  await page
    .getByRole("button", { name: "Try a real Diridon journey" })
    .click();
  await expect(page.locator(".selected-stop")).toContainText("Bay 11");
  await page.getByRole("button", { name: "Access gaps", exact: true }).click();
  await expect(page.locator(".gap-ranking li")).toHaveCount(10);
  await page.locator(".gap-ranking button").first().click();
  await expect(page.locator(".study-detail")).toContainText("Standard network");
  await page.getByRole("button", { name: "Prepare a letter" }).click();
  await expect(page.getByLabel("Review and edit before sending")).toHaveValue(
    /Please assess pedestrian access/,
  );
});
