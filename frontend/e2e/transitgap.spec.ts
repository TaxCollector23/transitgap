import { expect, test, type Page } from "@playwright/test";
const api = "http://127.0.0.1:8000";
async function open(page: Page) {
  await page.goto("/app");
  await expect(page.locator(".dataset-status.is-ready")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect(page.locator(".map-loading")).toHaveCount(0, {
    timeout: 20_000,
  });
}
async function example(page: Page) {
  await page
    .getByRole("button", { name: "Try a real Diridon journey" })
    .click();
  await expect(page.locator(".selected-stop")).toContainText("Bay 11");
}
async function route(page: Page) {
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/route") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Find Route", exact: true }).click();
  const r = await pending;
  expect(r.status()).toBe(200);
  await expect(
    page.getByRole("region", { name: "Route details" }),
  ).toBeVisible();
  await expect(page.locator(".map")).toHaveAttribute(
    "data-route-state",
    "current",
  );
  return r.json();
}

test("landing scrolls on desktop and phone, contains real study and opens app", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /The shortest route/ }),
    ).toBeVisible();
    await page.locator(".landing-footer").scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => scrollY)).toBeGreaterThan(200);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await expect(
      page.locator(".landing-eyebrow,.eyebrow,.method-icon"),
    ).toHaveCount(0);
    await page.screenshot({
      path: `test-artifacts/screenshots/landing-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("link", { name: "Open TransitGap" }).click();
  await expect(page.locator(".dataset-status.is-ready")).toBeVisible({
    timeout: 30_000,
  });
  await page.reload();
  await expect(page.locator(".dataset-status.is-ready")).toBeVisible();
});

test("real county routes, all five algorithms, mobility profiles and no repeated map fitting on text edits", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);
  await example(page);
  let result = await route(page);
  expect(result.profile).toBe("wheelchair");
  expect(result.segments.length).toBeGreaterThan(0);
  await expect(page.locator(".route-result")).toContainText("mi");
  await expect(page.locator(".route-result")).toContainText(
    "not field checked",
  );
  await page.locator(".advanced-settings summary").click();
  for (const algorithm of [
    "dijkstra",
    "bidirectional_dijkstra",
    "astar",
    "bellman_ford",
    "breadth_first",
  ]) {
    await page.getByLabel("Routing algorithm").selectOption(algorithm);
    result = await route(page);
    expect(result.algorithm).toBe(algorithm);
  }
  for (const profile of [
    "standard",
    "wheelchair",
    "stroller",
    "low_vision",
    "prefer_documented_paths",
  ]) {
    await page.getByLabel("Route profile").selectOption(profile);
    result = await route(page);
    expect(result.profile).toBe(profile);
  }
  await page.waitForTimeout(650);
  await page.evaluate(() => {
    const w = window as any;
    w.__fitCalls = 0;
    const map = w.__transitGapMap;
    const old = map.fitBounds.bind(map);
    map.fitBounds = (...args: any[]) => {
      w.__fitCalls++;
      return old(...args);
    };
  });
  await page.getByLabel("Search VTA stops").fill("Mountain View");
  await expect(page.locator(".stop-option").first()).toBeVisible();
  expect(await page.evaluate(() => (window as any).__fitCalls)).toBe(0);
  expect(errors).toEqual([]);
});

test("mobility detour, actual directions, scheduled service and share links", async ({
  page,
}) => {
  await open(page);
  await example(page);
  await route(page);
  await page
    .getByRole("button", { name: "Compare with standard route" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Mobility detour" }),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByText("Directions", { exact: true }).click();
  await expect(page.locator(".directions>li").first()).toContainText(/Head/);
  await page.getByText("Stop service & boarding", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Scheduled, not real-time" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Copy journey link" }).click();
  await expect(page).toHaveURL(/lat=.*stop=/);
  await page.reload();
  await expect(page.locator(".selected-stop")).toContainText("Bay 11");
  await expect(
    page.getByRole("button", { name: "Find Route", exact: true }),
  ).toBeEnabled();
});

test("network gaps render and create an editable factual letter", async ({
  page,
}) => {
  await open(page);
  await page.getByRole("button", { name: "Access gaps", exact: true }).click();
  await expect(page.locator(".gap-ranking li")).toHaveCount(10);
  await page.locator(".gap-ranking button").first().click();
  await expect(page.locator(".study-detail")).toContainText(
    "Standard network",
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Prepare a letter" }).click();
  await expect(page.getByLabel("Review and edit before sending")).toHaveValue(
    /Please assess pedestrian access/,
  );
  await page
    .getByLabel("Review and edit before sending")
    .fill("My reviewed draft");
  await expect(
    page.getByText("This draft has not been sent.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-artifacts/screenshots/access-gap.png" });
});

test("mobile map selection, distinct A and B pins, cancellation and route fit", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 37.32875, longitude: -121.90442 });
  await open(page);
  await page
    .getByRole("button", { name: "Choose on map", exact: true })
    .click();
  await expect(page.locator(".panel")).toHaveClass(/panel-collapsed/);
  await page.keyboard.press("Escape");
  await expect(page.locator(".panel")).toHaveClass(/panel-expanded/);
  await page.getByRole("button", { name: "Use my location" }).click();
  await page.getByLabel("Search VTA stops").fill("San Jose Diridon (Bay 11)");
  await page.locator(".stop-option").first().click();
  await route(page);
  await page.getByRole("button", { name: "Collapse route planner" }).click();
  await expect(page.locator(".map-marker-origin")).toBeVisible();
  await expect(page.locator(".map-marker-destination")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-artifacts/screenshots/mobile-route.png",
  });
  await page.getByRole("button", { name: "Expand route planner" }).click();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(
    page.locator(".map-marker-origin,.map-marker-destination"),
  ).toHaveCount(0);
});

test("failure recovery and out-of-county location", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 37.8, longitude: -122.4 });
  await open(page);
  await page.getByRole("button", { name: "Use my location" }).click();
  await expect(page.getByRole("alert")).toContainText("outside the supported");
  await example(page);
  await page.route("**/route", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Temporary outage" }),
    }),
  );
  await page.getByRole("button", { name: "Find Route", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Temporary outage");
  await page.unroute("**/route");
  await route(page);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("evidence loads only on request and stays distinct from field verification", async ({
  page,
}) => {
  const evidence: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/accessibility/")) evidence.push(r.url());
  });
  await open(page);
  expect(evidence).toHaveLength(0);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sidewalk data gaps" }),
  ).toBeVisible();
  await expect(page.locator(".gap-item").first()).toBeVisible();
  await page.locator(".gap-item").first().click();
  await expect(
    page.getByText("Evidence detail", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".eyebrow")).toHaveCount(0);
  const health = await page.request.get(`${api}/health`);
  expect((await health.json()).ready).toBe(true);
});
