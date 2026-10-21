import { test, expect } from "@playwright/test";

for (const viewport of [{width:1440,height:900},{width:390,height:844},{width:768,height:1024},{width:1920,height:1080}]) {
  test(`built map fills ${viewport.width}px viewport while routing is stalled`, async ({ page }) => {
    await page.setViewportSize(viewport);
    let healthRequests = 0;
    let bootstrapRequests = 0;
    const glyphRequests: string[] = [];
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      if (request.url().includes(".pbf")) glyphRequests.push(request.url());
    });
    // Hold the cold backend indefinitely. Map readiness must be independent.
    await page.route("**/routing/initialize", () => { healthRequests++; });
    await page.route("**/bootstrap.json", async route => {
      bootstrapRequests++;
      await route.fulfill({json:{
        coverage:{center:{latitude:37.2,longitude:-121.75},radius_m:70000,
          region:"Santa Clara County",description:"Startup test fixture",
          bounds:{west:-122.2,south:36.9,east:-121.2,north:37.5}},
        stops:[
          {stop_id:"a",stop_name:"Startup test stop",latitude:37.3296,longitude:-121.903},
          {stop_id:"b",stop_name:"Startup test neighbor",latitude:37.3297,longitude:-121.9031},
        ],
      }});
    });
    // Deterministic raster bytes: this regression checks layout and interaction,
    // not the availability or speed of a third-party tile host.
    await page.route("https://tile.openstreetmap.org/**", route => route.fulfill({
      contentType:"image/png",
      body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII=","base64"),
    }));
    await page.goto("/app");
    await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
    // A visible canvas can still be clipped by a zero-height parent. Check both.
    await expect.poll(async () => page.locator(".map").evaluate(el => ({
      width:Math.round(el.getBoundingClientRect().width),
      height:Math.round(el.getBoundingClientRect().height),
      position:getComputedStyle(el).position,
    }))).toEqual({...viewport,position:"absolute"});
    await expect(page.locator('.map[data-map-state="ready"]')).toBeVisible();
    expect(await page.locator(".maplibregl-canvas").boundingBox()).toMatchObject(viewport);
    await page.getByRole("button",{name:"Choose on map",exact:true}).click();
    await page.locator(".maplibregl-canvas").click({position:{x:viewport.width/2+(viewport.width>760?90:0),y:viewport.height/2}});
    await expect(page.locator(".map-marker-origin")).toBeVisible();
    expect(healthRequests).toBeGreaterThan(0);
    expect(bootstrapRequests).toBe(1);
    expect(glyphRequests).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test("cold startup failure keeps a valid trip actionable and retryable", async ({page}) => {
  let ready=false, routes=0;
  await page.route("**/bootstrap.json", route=>route.fulfill({json:{
    coverage:{center:{latitude:37.3296,longitude:-121.903},radius_m:1500,region:"Diridon",description:"Synthetic startup fixture"},
    stops:[{stop_id:"fixture",stop_name:"San Jose Diridon (Bay 11)",latitude:37.3296,longitude:-121.903}],
  }}));
  await page.route("**/routing/initialize", route=>route.fulfill({json:{alive:true,ready,error:ready?null:"synthetic startup failure"}}));
  await page.route("**/route",route=>{ routes++;return route.fulfill({status:503,json:{detail:"Synthetic route-service outage"}}); });
  await page.goto("/app");
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByRole("button",{name:"Try an example trip near Diridon Station"}).click();
  await expect(page.getByRole("button",{name:"Find route",exact:true})).toBeEnabled();
  await page.getByRole("button",{name:"Find route",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Try again");
  await expect(page.getByRole("button",{name:"Change destination"})).toBeVisible();
  ready=true;
  await page.getByRole("alert").getByRole("button",{name:"Try again",exact:true}).click();
  await expect.poll(()=>routes).toBe(1);
  await expect(page.getByRole("alert")).toContainText("Try again");
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
});
