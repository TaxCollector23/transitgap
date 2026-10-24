import { expect, test, type Page } from "@playwright/test";

const start = ["37.32875", "-121.90442"];

async function setStart(page: Page) {
  await page.getByText("Enter coordinates instead", { exact: true }).click();
  await page.getByLabel("Latitude", { exact: true }).fill(start[0]);
  await page.getByLabel("Longitude", { exact: true }).fill(start[1]);
  await page.getByRole("button", { name: "Use coordinates", exact: true }).click();
}

async function addDuplicateStops(page: Page, addDiridonExample = false) {
  await page.route("**/stops", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const original = data.stops.find((stop: { stop_id: string }) => stop.stop_id === "ci-stop");
    if (original) {
      Object.assign(original, {
        stop_name: "Santa Clara & Delmas",
        direction: "Eastbound",
        stop_description: "Eastbound",
        stop_code: "60409",
        agency: "vta",
        agency_name: "VTA",
        modes: ["bus"],
        routes_served: ["22", "64A", "64B", "68"],
      });
      data.stops.push({
        ...original,
        stop_id: "ci-stop-west",
        stop_name: "Santa Clara & Delmas",
        direction: "Westbound",
        stop_description: "Westbound",
        stop_code: "60444",
        latitude: 37.329,
        longitude: -121.9041,
      });
    }
    if (addDiridonExample) data.stops.push({
      stop_id: "ci-diridon-example",
      stop_name: "San Jose Diridon (Bay 11)",
      latitude: 37.32875,
      longitude: -121.9043,
      agency: "vta",
      agency_name: "VTA",
      platform_name: "Bay 11",
      modes: ["bus"],
      routes_served: ["68"],
      wheelchair_boarding: 0,
    });
    await route.fulfill({ response, json: data });
  });
}

test("same-name stops are distinct in search, selection, and About", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await addDuplicateStops(page);
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await setStart(page);
  const search = page.getByRole("combobox", { name: "Where are you going?" });
  await search.fill("Santa Clara & Delmas");
  await expect(page.getByRole("option", { name: /Eastbound/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /Westbound/ })).toBeVisible();
  await expect(page.locator(".stop-results")).not.toContainText("ci-stop");

  await page.getByRole("option", { name: /Westbound/ }).click();
  await expect(page.locator(".field-value").nth(1)).toContainText("Westbound");
  await page.getByRole("button", { name: /Change destination/ }).click();
  await search.fill("Santa Clara & Delmas");
  await page.getByRole("option", { name: /Eastbound/ }).click();
  await expect(page.locator(".field-value").nth(1)).toContainText("Eastbound");
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(page.locator(".route-result")).toBeVisible();
  const about = page.getByText("About Santa Clara & Delmas — Eastbound", { exact: true });
  await expect(about).toBeVisible();
  await about.click();
  await expect(page.locator(".platform-service h4")).toContainText("Eastbound");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("county and Diridon pilot boundaries are labeled and explained", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/coverage", async (route) => {
    const response = await route.fetch();
    const coverage = await response.json();
    await route.fulfill({
      response,
      json: {
        ...coverage,
        region: "Santa Clara County",
        center: { latitude: 37.25, longitude: -121.93 },
        bounds: { west: -122.2, south: 36.9, east: -121.2, north: 37.55 },
        boundary: {
          type: "Polygon",
          coordinates: [[[-122.2, 36.9], [-121.2, 36.9], [-121.2, 37.55], [-122.2, 37.55], [-122.2, 36.9]]],
        },
      },
    });
  });
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(page.getByLabel("Outline of Santa Clara County route coverage")).toBeVisible();
  await expect(page.locator(".map-coverage-badge svg path")).toHaveAttribute("d", /M/);
  await page.getByText("Map key", { exact: true }).click();
  await expect(page.getByText("Santa Clara County route coverage boundary")).toBeVisible();
  await expect(page.getByText("Diridon pilot: detailed City sidewalk records")).toBeVisible();
  await page.waitForFunction(() => Boolean((window as Window & { __transitGapMap?: { getLayer: (id: string) => unknown } }).__transitGapMap?.getLayer("coverage-edge")));
  await page.evaluate(() => (window as Window & { __transitGapMap?: { setZoom: (zoom: number) => void } }).__transitGapMap?.setZoom(9.5));
  await page.waitForFunction(() => Boolean((window as Window & { __transitGapMap?: { getLayer: (id: string) => unknown } }).__transitGapMap?.getLayer("coverage-label")));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("sidewalk review leads with a human location and keeps scores in technical detail", async ({ page }) => {
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByRole("button", { name: "For cities and advocates" }).click();
  const firstItem = page.locator(".gap-item").first();
  await expect(firstItem).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".advocate-overview")).not.toContainText(/Checking the Diridon pilot|Loading sidewalk review records/);
  await expect(firstItem).toContainText(/Near .* — /);
  await expect(firstItem).not.toContainText(/route proximity|\b\d+\/100\b/i);
  await firstItem.click();
  await expect(page.locator(".gap-detail")).toContainText("inspection suggestions, not confirmed barriers");
  await expect(page.getByText(/Review priority score:/)).toBeHidden();
  await page.getByText("Technical detail", { exact: true }).click();
  await expect(page.getByText(/Review priority score: .*proximity-based review priority, not a measure of barrier severity/)).toBeVisible();
});

test("a stalled route request times out promptly and retry succeeds", async ({ page }) => {
  let attempts = 0;
  await page.route("**/route", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await new Promise((resolve) => setTimeout(resolve, 14_000));
      try { await route.continue(); } catch { /* The client timeout has already cancelled this request. */ }
      return;
    }
    if (attempts === 3) {
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await setStart(page);
  const search = page.getByRole("combobox", { name: "Where are you going?" });
  await search.fill("SYNTHETIC CI Stop");
  await page.getByRole("option", { name: /SYNTHETIC CI Stop/ }).click();
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(page.getByText(/did not finish within 12 seconds/)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator(".route-result")).toBeVisible({ timeout: 8_000 });
  await page.getByRole("radio", { name: "Wheelchair", exact: true }).check();
  await expect(page.getByText("TransitGap is having trouble connecting.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator(".route-result")).toBeVisible({ timeout: 8_000 });
});

test("profile follows one persistence rule through examples, clear, new trip, and reload", async ({ page }) => {
  await addDuplicateStops(page, true);
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByRole("radio", { name: "Wheelchair", exact: true }).check();
  await page.getByRole("button", { name: "Try an example trip near Diridon Station" }).click();
  await expect(page.getByRole("radio", { name: "Wheelchair", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Clear trip / Start over" }).click();
  await expect(page.getByRole("radio", { name: "Walking", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Wheelchair", exact: true }).check();

  await setStart(page);
  const search = page.getByRole("combobox", { name: "Where are you going?" });
  await search.fill("Santa Clara & Delmas");
  await page.getByRole("option", { name: /Eastbound/ }).click();
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(page.locator(".route-result")).toBeVisible();
  await page.getByRole("button", { name: "Plan a new trip" }).click();
  await expect(page.getByRole("radio", { name: "Wheelchair", exact: true })).toBeChecked();
  await page.reload();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(page.getByRole("radio", { name: "Wheelchair", exact: true })).toBeChecked();
  await expect(page.locator(".field-value")).toHaveCount(0);

  await page.goto("/app?lat=37.32875&lon=-121.90442&stop=ci-stop&profile=wheelchair");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(page.getByRole("radio", { name: "Wheelchair", exact: true })).toBeChecked();
  await expect(page.locator(".field-value").nth(1)).toContainText("Eastbound");
  await page.goto("/");
  await expect(page.locator(".landing-art")).toBeVisible();
  await page.goBack();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(page.getByRole("radio", { name: "Wheelchair", exact: true })).toBeChecked();
  await expect(page.locator(".field-value").nth(1)).toContainText("Eastbound");
  await page.goForward();
  await expect(page.locator(".landing-art")).toBeVisible();
});
