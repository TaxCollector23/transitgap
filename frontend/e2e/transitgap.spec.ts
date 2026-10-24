import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const shots = "test-artifacts/screenshots";

// Real county journeys, one per agency.
const JOURNEYS = {
  vta: { name: "VTA", origin: [37.32875, -121.90442], query: "San Jose Diridon (Bay 11)", option: /San Jose Diridon \(Bay 11\)/ },
  caltrain: { name: "Caltrain", origin: [37.3452, -121.977], query: "Santa Clara Caltrain", option: /Santa Clara Caltrain Station/ },
  bart: { name: "BART", origin: [37.364, -121.882], query: "Berryessa", option: /Berryessa \/ North San JoseBART station/ },
} as const;

async function open(page: Page) {
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
}

async function startAt(page: Page, [lat, lon]: readonly number[]) {
  await page.getByText("Enter coordinates instead", { exact: true }).click();
  await page.getByLabel("Latitude", { exact: true }).fill(String(lat));
  await page.getByLabel("Longitude", { exact: true }).fill(String(lon));
  await page.getByRole("button", { name: "Use coordinates" }).click();
  await expect(page.getByRole("button", { name: "Change starting point" })).toBeVisible();
}

const stopOptions = (page: Page) => page.getByRole("listbox", { name: "Transit stops and stations" }).getByRole("option");

async function goTo(page: Page, query: string, option: RegExp) {
  const box = page.getByRole("combobox", { name: "Where are you going?" });
  await box.fill(query);
  await stopOptions(page).filter({ hasText: option }).first().click();
  await expect(page.getByRole("button", { name: "Change destination" })).toBeVisible();
}

async function findRoute(page: Page) {
  const pending = page.waitForResponse((r) => r.url().endsWith("/route") && r.request().method() === "POST", { timeout: 60_000 });
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 2, name: /^To / })).toBeVisible();
  await expect(page.locator(".map")).toHaveAttribute("data-route-state", "current");
  return response.json();
}

function checkDirections(result: { directions: Array<{ instruction: string; distance_m: number }>; distance_m: number }) {
  const instructions = result.directions.map((d) => d.instruction);
  for (const text of instructions) {
    expect(text).not.toMatch(/unnamed|Information missing/i);
  }
  const total = result.directions.reduce((sum, d) => sum + d.distance_m, 0);
  expect(Math.abs(total - result.distance_m)).toBeLessThan(1);
  // No two identical consecutive instructions (the old one-per-edge output).
  for (let i = 1; i < instructions.length; i++)
    expect(`${instructions[i - 1]}|${instructions[i]}`).not.toBe(`${instructions[i]}|${instructions[i]}`);
}

test("1. the primary task is obvious on first open", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "Where are you starting?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where are you going?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How do you travel?" })).toBeVisible();
  const next = page.getByRole("button", { name: "Choose a starting point", exact: true });
  await expect(next).toBeVisible();
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.locator('#origin-title')).toBeFocused();
  await expect(page.locator("#route-missing")).toHaveText("Choose where you're starting and where you're going.");
  await expect(page.getByRole("radio", { name: "Walking" })).toBeChecked();
  // No tutorial, dashboard tabs or technical status text on the first screen.
  await expect(page.locator(".app-tabs, .dataset-status")).toHaveCount(0);
  expect(await page.locator(".panel").innerText()).not.toMatch(/GTFS|graph|algorithm|segment/i);
  await page.screenshot({ path: `${shots}/desktop-1440-first-open.png` });
});

test("2-3. find a stop by name and agency, and set an origin without the map", async ({ page }) => {
  await open(page);
  await startAt(page, JOURNEYS.bart.origin);
  const box = page.getByRole("combobox", { name: "Where are you going?" });
  await box.fill("berryessa");
  await expect(stopOptions(page).filter({ hasText: /BART station/ })).toHaveCount(1);
  await expect(stopOptions(page).filter({ hasText: /VTA bus stop/ }).first()).toBeVisible();
  await page.getByText("Filter by agency", { exact: true }).click();
  await page.getByRole("radio", { name: "BART" }).check();
  await expect(stopOptions(page)).toHaveCount(1);
  await page.getByRole("radio", { name: "Caltrain" }).check();
  await box.fill("santa clara");
  await expect(stopOptions(page).filter({ hasText: /Santa Clara Caltrain Station/ })).toHaveCount(1);
  // Platforms are grouped into one station, not listed twice.
  await expect(stopOptions(page).filter({ hasText: /Northbound|Southbound/ })).toHaveCount(0);
  await page.getByRole("radio", { name: "All" }).check();
  await box.fill("");
  await expect(stopOptions(page).first()).toBeVisible();
});

for (const viewport of [{width:390,height:844},{width:768,height:1024},{width:1440,height:900},{width:1920,height:1080}])
for (const key of ["vta", "caltrain", "bart"] as const) {
  test(`4-7. ${JOURNEYS[key].name} ${viewport.width}px journey: route, profile change, directions and missing data`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const journey = JOURNEYS[key];
    await open(page);
    await startAt(page, journey.origin);
    await goTo(page, journey.query, journey.option);
    const walking = await findRoute(page);
    expect(walking.profile).toBe("standard");
    checkDirections(walking);
    expect(walking.directions.length).toBeLessThanOrEqual(20);
    await expect(page.locator(".directions > li")).toHaveCount(walking.directions.length);
    await expect(page.locator(".route-headline")).toContainText("Walking");
    await page.screenshot({ path: `${shots}/${viewport.width}-${key}-walking.png` });

    // 5. Changing the profile recalculates; the old route is never shown as current.
    const pending = page.waitForResponse((r) => r.url().endsWith("/route") && r.request().method() === "POST", { timeout: 60_000 });
    await page.getByRole("radio", { name: "Wheelchair" }).check();
    const wheelchairResponse = await pending;
    const wheelchair = await wheelchairResponse.json();
    expect(wheelchairResponse.request().postDataJSON().profile).toBe("wheelchair");
    expect(wheelchair.profile).toBe("wheelchair");
    await expect(page.locator(".route-headline")).toContainText("Wheelchair");
    checkDirections(wheelchair);

    // 6-7. Readable directions and one route-level missing-data message.
    await expect(page.locator(".directions > li").first()).toContainText(/Head|Go from/);
    await expect(page.getByText("Information missing")).toHaveCount(0);
    await expect(page.locator(".route-limitations")).toContainText("Some accessibility information is missing along this route.");
    await page.locator("summary", { hasText: "Accessibility details" }).click();
    await expect(page.locator(".route-result")).toContainText(/not recorded for/);
    await page.locator("summary", { hasText: /^About / }).click();
    await expect(page.locator(".stop-service")).toContainText(/boarding/i);
    await page.screenshot({ path: `${shots}/${viewport.width}-${key}-wheelchair-details.png`, fullPage: false });
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(axe.violations.map((v) => v.id)).toEqual([]);
    for (const label of ["Stroller", "Low vision"]) {
      const next = page.waitForResponse(r => r.url().endsWith("/route") && r.request().method() === "POST");
      await page.getByRole("radio", {name:label,exact:true}).check();
      expect((await next).status()).toBe(200);
      await expect(page.locator(".route-headline")).toContainText(label);
    }
  });
}

test("all five profiles and five algorithms still route", async ({ page }) => {
  await open(page);
  await startAt(page, JOURNEYS.vta.origin);
  await goTo(page, JOURNEYS.vta.query, JOURNEYS.vta.option);
  await findRoute(page);
  await page.getByRole("button", { name: "Edit trip" }).click();
  await page.getByText("Advanced options", { exact: true }).click();
  for (const algorithm of ["dijkstra", "bidirectional_dijkstra", "astar", "bellman_ford", "breadth_first"]) {
    if (!(await page.getByLabel("Routing algorithm").isVisible())) await page.getByText("Advanced options", { exact: true }).click();
    await page.getByLabel("Routing algorithm").selectOption(algorithm);
    const result = await findRoute(page);
    expect(result.algorithm).toBe(algorithm);
    await page.getByRole("button", { name: "Edit trip" }).click();
  }
  if (!(await page.getByLabel("Routing algorithm").isVisible())) await page.getByText("Advanced options", { exact: true }).click();
  await page.getByLabel("Routing algorithm").selectOption("astar");
  for (const profile of ["Walking", "Wheelchair", "Stroller", "Low vision"]) {
    await page.getByRole("radio", { name: profile, exact: true }).check();
    const result = await findRoute(page);
    expect(result.profile).toBe({ Walking: "standard", Wheelchair: "wheelchair", Stroller: "stroller", "Low vision": "low_vision" }[profile]);
    await page.getByRole("button", { name: "Edit trip" }).click();
  }
  if (!(await page.getByLabel("Routing algorithm").isVisible())) await page.getByText("Advanced options", { exact: true }).click();
  await page.getByLabel("Prefer paths with documented accessibility information").check();
  expect((await findRoute(page)).profile).toBe("prefer_documented_paths");
});

test("8-9. access gaps and reporting are one step away and return without losing the route", async ({ page }) => {
  await open(page);
  await startAt(page, JOURNEYS.vta.origin);
  await goTo(page, JOURNEYS.vta.query, JOURNEYS.vta.option);
  await findRoute(page);
  await page.getByRole("button", { name: "Which stops are harder to reach by wheelchair?" }).click();
  await expect(page.getByRole("heading", { name: "Which stops are harder to reach by wheelchair?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where is accessibility information missing near a stop?" })).toBeVisible();
  await expect(page.locator(".gap-ranking li").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "← Back to route planning" }).click();
  await expect(page.getByRole("heading", { name: /^To San Jose Diridon/ })).toBeVisible();
  await page.getByRole("button", { name: "Report an issue" }).click();
  await expect(page.getByRole("heading", { name: "Report an issue", exact: true })).toBeVisible();
  const reportPanel = page.locator(".report-panel");
  const reportLocation = reportPanel.getByRole("heading", { name: "1. Where is the problem?" });
  const reportStatus = reportPanel.getByRole("status");
  await expect.poll(async () => {
    if (await reportLocation.isVisible().catch(() => false)) return true;
    const status = await reportStatus.textContent().catch(() => "");
    return /paused|still getting ready|availability couldn't be checked/i.test(status || "");
  }, { timeout: 12_000 }).toBe(true);
  if (await reportLocation.isVisible()) {
    await expect(page.getByLabel("2. What's the problem?")).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit report" })).toBeDisabled();
    await expect(page.locator("#report-submit-hint")).toContainText("Choose where the problem is");
  } else {
    await expect(reportStatus).toContainText(/Community reports are paused|TransitGap is still getting ready|Reporting availability couldn't be checked/i);
    if (!/Community reports are paused/.test(await reportStatus.textContent() || ""))
      await expect(reportPanel.getByRole("button", { name: "Try checking again" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit report" })).toHaveCount(0);
  }
  await page.screenshot({ path: `${shots}/desktop-1440-report.png` });
  await page.getByRole("button", { name: "← Back to route planning" }).click();
  await expect(page.getByRole("heading", { name: /^To San Jose Diridon/ })).toBeVisible();
});

test("10. the whole primary flow works with a keyboard only", async ({ page }) => {
  await open(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to route planner" })).toBeFocused();
  await page.getByText("Enter coordinates instead", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Latitude", { exact: true }).focus();
  await page.keyboard.type(String(JOURNEYS.vta.origin[0]));
  await page.keyboard.press("Tab");
  await page.keyboard.type(String(JOURNEYS.vta.origin[1]));
  await page.keyboard.press("Enter");
  const box = page.getByRole("combobox", { name: "Where are you going?" });
  await box.focus();
  await page.keyboard.type("Diridon (Bay 11)");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Change destination" })).toBeVisible();
  await page.getByRole("radio", { name: "Walking" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "Wheelchair" })).toBeChecked();
  const pending = page.waitForResponse((r) => r.url().endsWith("/route"), { timeout: 60_000 });
  await page.getByRole("button", { name: "Find route", exact: true }).focus();
  await page.keyboard.press("Enter");
  expect((await pending).status()).toBe(200);
  await expect(page.locator("#route-title")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
});

test("11. a backend outage keeps the map and the user's choices", async ({ page }) => {
  await open(page);
  await startAt(page, JOURNEYS.vta.origin);
  await goTo(page, JOURNEYS.vta.query, JOURNEYS.vta.option);
  await page.route("**/route", (r) => r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Temporary outage" }) }));
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("TransitGap is having trouble connecting. Your map is still available. Try again.");
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Change destination" })).toBeVisible();
  await page.screenshot({ path: `${shots}/desktop-1440-outage.png` });
  await page.unroute("**/route");
  const pending = page.waitForResponse((r) => r.url().endsWith("/route"), { timeout: 60_000 });
  await page.getByRole("alert").getByRole("button", { name: "Try again" }).click();
  expect((await pending).status()).toBe(200);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("out-of-area starting points are refused in plain language", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 37.8, longitude: -122.4 });
  await open(page);
  await page.getByRole("button", { name: "Use my location" }).click();
  await expect(page.getByRole("alert")).toContainText("outside the area TransitGap covers");
});

for (const key of ["vta", "caltrain", "bart"] as const) {
  test(`12. mobile ${JOURNEYS[key].name} journey at 390x844`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const journey = JOURNEYS[key];
    await open(page);
    if (key === "vta") await page.screenshot({ path: `${shots}/mobile-390-first-open.png` });
    await startAt(page, journey.origin);
    await goTo(page, journey.query, journey.option);
    const result = await findRoute(page);
    checkDirections(result);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    // The sheet leaves the map visible.
    const sheet = await page.locator(".panel").boundingBox();
    expect(sheet!.height).toBeLessThan(844 * 0.62);
    await expect(page.locator(".map-marker-origin")).toBeVisible();
    await expect(page.locator(".map-marker-destination")).toBeVisible();
    await page.screenshot({ path: `${shots}/mobile-390-${key}-summary.png` });
    await page.getByRole("button", { name: /Show \d+ directions/ }).click();
    await expect(page.getByRole("dialog", { name: /Directions to/ })).toBeVisible();
    await expect(page.getByRole("dialog").locator(".directions > li")).toHaveCount(result.directions.length);
    await page.screenshot({ path: `${shots}/mobile-390-${key}-directions.png` });
    await page.getByRole("button", { name: "Back to map" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Show more map" }).click();
    await expect(page.locator(".panel")).toHaveClass(/panel-collapsed/);
    await expect(page.locator(".sheet-summary")).toContainText(/^To /);
    await page.screenshot({ path: `${shots}/mobile-390-${key}-map.png` });
  });
}

test("map selection on mobile can be cancelled, and other stops can be shown during a route", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await page.getByRole("button", { name: "Choose on map", exact: true }).click();
  await expect(page.locator(".panel")).toHaveClass(/panel-collapsed/);
  await page.keyboard.press("Escape");
  await expect(page.locator(".panel")).toHaveClass(/panel-expanded/);
  await startAt(page, JOURNEYS.vta.origin);
  await goTo(page, JOURNEYS.vta.query, JOURNEYS.vta.option);
  await findRoute(page);
  const toggle = page.getByRole("button", { name: "Show other stops" });
  await toggle.click();
  await expect(page.getByRole("button", { name: "Hide other stops" })).toHaveAttribute("aria-pressed", "true");
});

test("trip links reopen the same trip", async ({ page }) => {
  await open(page);
  await startAt(page, JOURNEYS.caltrain.origin);
  await goTo(page, JOURNEYS.caltrain.query, JOURNEYS.caltrain.option);
  await findRoute(page);
  await page.getByRole("button", { name: "Copy link to this trip" }).click();
  await expect(page).toHaveURL(/lat=.*stop=caltrain/);
  await page.reload();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".field-value").nth(1)).toContainText("Santa Clara Caltrain Station");
  await expect(page.getByRole("button", { name: "Find route", exact: true })).toBeEnabled();
});
