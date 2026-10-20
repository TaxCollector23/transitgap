# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core.spec.ts >> synthetic CI fixture: keyboard route, profile changes, voice fallback and durable report
- Location: fixture-e2e/core.spec.ts:3:1

# Error details

```
Test timeout of 45000ms exceeded.
```

```
Error: locator.selectOption: Test timeout of 45000ms exceeded.
Call log:
  - waiting for getByLabel('Observation', { exact: true })
    - waiting for "http://127.0.0.1:5174/app" navigation to finish...
    - navigated to "http://127.0.0.1:5174/app"

```

# Page snapshot

```yaml
- main [ref=f1e3]:
  - link "Skip map to route controls" [ref=f1e4] [cursor=pointer]:
    - /url: "#origin-title"
  - region "Map" [ref=f1e5]:
    - application "Interactive map. Choose a starting point when map selection is active, or tap a VTA stop to choose your destination.":
      - region "Map" [ref=f1e6]
      - generic:
        - generic:
          - group [ref=f1e7]:
            - generic "Toggle attribution" [ref=f1e8] [cursor=pointer]
            - generic [ref=f1e9]: © OpenStreetMap contributors
          - generic [ref=f1e10]:
            - button "Zoom in" [ref=f1e11] [cursor=pointer]
            - button "Zoom out" [ref=f1e13] [cursor=pointer]
    - group [ref=f1e15]:
      - generic "Map key" [ref=f1e16] [cursor=pointer]
  - complementary "Route planner" [ref=f1e17]:
    - generic [ref=f1e18]:
      - generic [ref=f1e19]:
        - link "TransitGap home" [ref=f1e20] [cursor=pointer]:
          - /url: /
          - heading "TransitGap" [level=1] [ref=f1e21]
        - button "Report an issue" [ref=f1e22] [cursor=pointer]
        - button "Collapse route planner" [expanded] [ref=f1e23] [cursor=pointer]
      - navigation "Map views" [ref=f1e26]:
        - button "Route" [ref=f1e27] [cursor=pointer]
        - button "Access gaps" [ref=f1e28] [cursor=pointer]
        - button "Evidence" [ref=f1e29] [cursor=pointer]
      - generic [ref=f1e30]:
        - status [ref=f1e31]: 1 VTA stops
        - generic [ref=f1e32]:
          - button "Read aloud" [ref=f1e34] [cursor=pointer]
          - group [ref=f1e35]:
            - generic "Reading options" [ref=f1e36]
            - option "Current page" [selected]
            - option "Route summary"
            - option "Accessibility information"
            - option "Directions"
            - option "Selected transit stop"
            - option "0.75×"
            - option "1×" [selected]
            - option "1.25×"
            - option "1.5×"
            - option "Use available English voice" [selected]
            - option "Samantha"
            - option "Albert"
            - option "Bad News"
            - option "Bahh"
            - option "Bells"
            - option "Boing"
            - option "Bubbles"
            - option "Cellos"
            - option "Daniel"
            - option "Eddy (English (United States))"
            - option "Eddy (English (United Kingdom))"
            - option "Flo (English (United States))"
            - option "Flo (English (United Kingdom))"
            - option "Fred"
            - option "Good News"
            - option "Grandma (English (United States))"
            - option "Grandma (English (United Kingdom))"
            - option "Grandpa (English (United States))"
            - option "Grandpa (English (United Kingdom))"
            - option "Jester"
            - option "Junior"
            - option "Karen"
            - option "Kathy"
            - option "Moira"
            - option "Organ"
            - option "Ralph"
            - option "Reed (English (United States))"
            - option "Reed (English (United Kingdom))"
            - option "Rishi"
            - option "Rocko (English (United States))"
            - option "Rocko (English (United Kingdom))"
            - option "Sandy (English (United States))"
            - option "Sandy (English (United Kingdom))"
            - option "Shelley (English (United States))"
            - option "Shelley (English (United Kingdom))"
            - option "Superstar"
            - option "Tessa"
            - option "Trinoids"
            - option "Whisper"
            - option "Wobble"
            - option "Zarvox"
        - region [ref=f1e37]:
          - heading "Where are you starting?" [level=2] [ref=f1e38]
          - generic [ref=f1e39]:
            - button "Choose on map" [ref=f1e40] [cursor=pointer]
            - button "Use my location" [ref=f1e41] [cursor=pointer]
          - group [ref=f1e42]:
            - generic "Search an address" [ref=f1e43] [cursor=pointer]
        - region [ref=f1e44]:
          - heading "Which VTA stop?" [level=2] [ref=f1e45]
          - searchbox "Search VTA stops" [ref=f1e47]
        - generic [ref=f1e48]:
          - generic [ref=f1e49]: Travel profile
          - combobox "Route profile" [ref=f1e50]:
            - option "Standard"
            - option "Wheelchair" [selected]
            - option "Stroller"
            - option "Low vision"
            - option "Prefer documented paths"
        - button "Find Route" [disabled] [ref=f1e52]
        - button "Try a real Diridon journey" [ref=f1e53] [cursor=pointer]
        - group [ref=f1e54]:
          - generic "Under the hood" [ref=f1e55] [cursor=pointer]
          - option "Dijkstra"
          - option "Bidirectional Dijkstra"
          - option "A*" [selected]
          - option "Bellman–Ford"
          - option "Breadth-first search"
        - paragraph [ref=f1e58]: Mapped routes are not verified accessible. Missing tags and changing conditions can affect a journey.
        - generic [ref=f1e59]:
          - link "OpenStreetMap" [ref=f1e60] [cursor=pointer]:
            - /url: https://www.openstreetmap.org/copyright
          - link "VTA GTFS" [ref=f1e61] [cursor=pointer]:
            - /url: https://www.vta.org/go/developers
          - link "Data & limits" [ref=f1e62] [cursor=pointer]:
            - /url: /#methodology
  - status [ref=f1e63]: 1 VTA stops loaded for Diridon Station area
```

# Test source

```ts
  1  | import {test,expect} from '@playwright/test';
  2  | import AxeBuilder from '@axe-core/playwright';
  3  | test('synthetic CI fixture: keyboard route, profile changes, voice fallback and durable report',async({page})=>{
  4  |  await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aAl8AAAAASUVORK5CYII=','base64')}));
  5  |  await page.goto('/app');
  6  |  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  7  |  await expect(page.locator('.dataset-status.is-ready')).toBeVisible();
  8  |  await page.getByText('Search an address',{exact:true}).click();
  9  |  await page.getByText('Enter coordinates instead',{exact:true}).click();
  10 |  await page.getByLabel('Starting latitude').fill('37.32875');await page.getByLabel('Starting longitude').fill('-121.90442');
  11 |  await page.getByRole('button',{name:'Use coordinates',exact:true}).focus();await page.keyboard.press('Enter');
  12 |  await page.getByRole('searchbox',{name:'Search VTA stops'}).fill('SYNTHETIC');
  13 |  await page.getByRole('button',{name:/SYNTHETIC CI Stop/}).click();
  14 |  const distances=[];
  15 |  for(const profile of ['standard','wheelchair','stroller','low_vision']){
  16 |   await page.locator('#mobility-profile').selectOption(profile);
  17 |   const pending=page.waitForResponse(r=>r.url().endsWith('/route')&&r.request().method()==='POST');
  18 |   await page.getByRole('button',{name:'Find Route',exact:true}).focus();await page.keyboard.press('Enter');
  19 |   const response=await pending;expect(response.request().postDataJSON().profile).toBe(profile);expect(response.status()).toBe(200);distances.push((await response.json()).distance_m);
  20 |   await expect(page.getByRole('region',{name:'Route details'})).toBeVisible();
  21 |  }
  22 |  expect(distances[1]).toBeGreaterThan(distances[0]);
  23 |  await page.getByRole('button',{name:'Read aloud',exact:true}).click();
  24 |  if(await page.getByRole('button',{name:'Stop reading',exact:true}).isVisible())await page.getByRole('button',{name:'Stop reading',exact:true}).click();
  25 |  else await expect(page.getByText(/No local voice|isn't supported/)).toBeVisible();
  26 |  await page.getByRole('button',{name:'Report an issue',exact:true}).click();
  27 |  await expect(page.getByRole('heading',{name:'Report an issue',exact:true})).toBeVisible();
  28 |  await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
> 29 |  await page.getByLabel('Observation',{exact:true}).selectOption('pedestrian_pothole');
     |                                                    ^ Error: locator.selectOption: Test timeout of 45000ms exceeded.
  30 |  await page.getByLabel('Details optional').fill('SYNTHETIC CI persistence check, not a real observation.');
  31 |  await page.getByRole('button',{name:'Submit report'}).click();
  32 |  await expect(page.getByText('Report saved as unverified community evidence.')).toBeVisible();
  33 |  await page.reload();await page.getByRole('button',{name:'Evidence',exact:true}).click();
  34 |  await expect(page.getByText('SYNTHETIC CI persistence check, not a real observation.').first()).toBeVisible();
  35 |  const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();expect(axe.violations.map(v=>v.id)).toEqual([]);
  36 |  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  37 | });
  38 | 
```