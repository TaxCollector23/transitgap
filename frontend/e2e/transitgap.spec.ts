import { expect, test } from '@playwright/test'

const screenshotDir = 'test-artifacts/screenshots'

async function openApp(page: import('@playwright/test').Page) {
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  const apiFailures: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', (request) => {
    if (request.url().startsWith('http://localhost:8000/')) apiFailures.push(`${request.url()} ${request.failure()?.errorText || ''}`)
  })
  await page.goto('/app', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await expect(page.locator('.dataset-status.is-ready')).toContainText(/stops/)
  return { pageErrors, consoleErrors, apiFailures }
}

async function chooseRealStop(page: import('@playwright/test').Page, name: string) {
  await page.getByLabel('Search VTA stops').fill(name)
  const option = page.locator('.stop-option').filter({ hasText: name }).first()
  await expect(option).toBeVisible()
  await option.click()
  await expect(page.locator('.selected-stop')).toContainText(name)
}

async function clickStopMarker(page: import('@playwright/test').Page, stopId: string, coordinates: [number, number]) {
  await page.waitForFunction(() => {
    const map = (window as Window & { __transitGapMap?: any }).__transitGapMap
    return map?.loaded() && map.querySourceFeatures('vta-stops').length > 0
  })
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const hit = await page.evaluate(({ id, point }) => {
      const map = (window as Window & { __transitGapMap?: any }).__transitGapMap
      const projected = map.project(point)
      const features = map.queryRenderedFeatures(projected, { layers: ['vta-stops', 'stop-clusters'] })
      return {
        x: projected.x,
        y: projected.y,
        stopVisible: features.some((feature: any) => feature.layer.id === 'vta-stops' && feature.properties.stop_id === id),
      }
    }, { id: stopId, point: coordinates })
    await page.mouse.click(hit.x, hit.y)
    if (hit.stopVisible) break
    await page.waitForTimeout(350)
  }
  await expect(page.locator('.selected-stop')).toContainText('San Jose Diridon (Bay 11)')
}

async function routeAndReadRequest(page: import('@playwright/test').Page) {
  const responsePromise = page.waitForResponse((response) => response.url().endsWith('/route') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Find Route' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  const request = JSON.parse(response.request().postData() || '{}')
  const body = await response.json()
  expect(body.geometry.type).toBe('LineString')
  expect(body.distance_m).toBeGreaterThan(0)
  if (body.accessibility) {
    expect(body.accessibility.distance_denominator_m).toBeGreaterThanOrEqual(0)
    expect(body.accessibility.surface_distance_known_m + body.accessibility.surface_distance_missing_m).toBeGreaterThanOrEqual(0)
    expect(body.optimization_cost_m).toBeGreaterThanOrEqual(body.distance_m - (body.accessibility.connector_distance_m || 0) - 0.2)
  }
  await expect(page.getByText('ROUTE FOUND')).toBeVisible()
  await expect(page.locator('.map')).toHaveAttribute('data-route-state', 'current')
  await page.waitForTimeout(550)
  await expect(page.locator('.map-marker-origin')).toBeVisible()
  await expect(page.locator('.map-marker-destination')).toBeVisible()
  return { request, body }
}

test('the editorial home opens the planner and direct planner URLs refresh', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Can you get to the stop on foot\?/ })).toBeVisible()
  await page.getByRole('link', { name: 'Plan a walk' }).click()
  await expect(page).toHaveURL(/\/app$/)
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible({ timeout: 20_000 })
  await page.reload()
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible({ timeout: 20_000 })
})

test('desktop route planning uses real VTA data and every routing choice', async ({ page, context }) => {
  const initialCalls = { health: 0, coverage: 0, stops: 0 }
  page.on('request', (request) => {
    const endpoint = new URL(request.url()).pathname.slice(1)
    if (endpoint in initialCalls) initialCalls[endpoint as keyof typeof initialCalls] += 1
  })
  const diagnostics = await openApp(page)
  expect(initialCalls).toEqual({ health: 1, coverage: 1, stops: 1 })
  await page.screenshot({ path: `${screenshotDir}/final-desktop-initial.png` })
  const findRoute = page.getByRole('button', { name: 'Find Route' })
  await expect(findRoute).toBeDisabled()

  await page.getByRole('button', { name: 'Choose on map' }).click()
  await expect(page.locator('.map-selection-banner')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.map-selection-banner')).toHaveCount(0)
  await page.getByRole('button', { name: 'Choose on map' }).click()
  await page.waitForFunction(() => {
    const map = (window as Window & { __transitGapMap?: any }).__transitGapMap
    return map?.loaded() && map.querySourceFeatures('vta-stops').length > 0
  })
  const stopPoint = await page.evaluate(() => {
    const map = (window as Window & { __transitGapMap?: any }).__transitGapMap
    const point = map.project([-121.902321, 37.330463])
    return { x: point.x, y: point.y }
  })
  await page.mouse.click(stopPoint.x, stopPoint.y)
  await expect(page.locator('.map-marker-origin')).toBeVisible()
  await expect(page.locator('.selected-stop')).toHaveCount(0)
  await expect(page.locator('.map-selection-banner')).toHaveCount(0)
  await page.getByRole('button', { name: 'Change starting point' }).click()
  await page.getByRole('button', { name: 'Choose on map' }).click()
  const startPoint = await page.evaluate(() => {
    const map = (window as Window & { __transitGapMap?: any }).__transitGapMap
    const point = map.project([-121.90442, 37.32875])
    return { x: point.x, y: point.y }
  })
  await page.mouse.click(startPoint.x, startPoint.y)
  await expect(page.locator('.map-marker-origin')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Find Route' })).toBeDisabled()
  await page.getByRole('button', { name: 'Change starting point' }).click()
  await expect(page.locator('.map-marker-origin')).toHaveCount(0)
  await page.getByRole('button', { name: 'Choose on map' }).click()
  await page.getByRole('button', { name: 'Cancel map selection' }).click()
  await expect(page.locator('.map-selection-banner')).toHaveCount(0)

  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 37.32875, longitude: -121.90442 })
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.locator('.map-marker-origin')).toBeVisible()
  await page.screenshot({ path: `${screenshotDir}/round2-origin-selected.png` })
  await page.getByLabel('Search VTA stops').fill('San Jose Diridon (Bay 11)')
  await expect(page.locator('.stop-option').filter({ hasText: 'San Jose Diridon (Bay 11)' })).toBeVisible()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(page.locator('.stop-option').filter({ hasText: 'San Jose Diridon (Bay 11)' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('.selected-stop')).toContainText('San Jose Diridon (Bay 11)')
  await page.screenshot({ path: `${screenshotDir}/round2-stop-selected.png` })
  await page.getByRole('button', { name: 'Change', exact: true }).click()
  await clickStopMarker(page, '4514', [-121.902321, 37.330463])
  await expect(page.locator('.map-marker-destination')).toBeVisible()

  const initial = await routeAndReadRequest(page)
  expect(initial.request).toMatchObject({ algorithm: 'dijkstra', profile: 'standard', destination_stop_id: '4514' })
  await page.screenshot({ path: `${screenshotDir}/round2-route-desktop.png` })
  await page.screenshot({ path: `${screenshotDir}/final-desktop-route.png` })
  await expect(page.locator('.route-result')).toContainText(/walking distance/)
  await expect(page.locator('.route-result')).toContainText(/not verified accessible/)

  await page.locator('.advanced-settings summary').click()
  const algorithmLabels: Record<string, string> = { bidirectional_dijkstra: 'Bidirectional Dijkstra', astar: 'A*', bellman_ford: 'Bellman–Ford', breadth_first: 'Breadth-first search' }
  for (const algorithm of ['bidirectional_dijkstra', 'astar', 'bellman_ford', 'breadth_first']) {
    await page.getByLabel('Routing algorithm').selectOption(algorithm)
    await expect(page.getByText('ROUTE NEEDS AN UPDATE')).toBeVisible()
    await expect(page.locator('.map')).toHaveAttribute('data-route-state', 'clear')
    const result = await routeAndReadRequest(page)
    expect(result.request.algorithm).toBe(algorithm)
    await expect(page.locator('.route-result')).toContainText(algorithmLabels[algorithm])
  }

  await page.getByRole('button', { name: /Avoid mapped stairs/ }).click()
  await expect(page.getByText('ROUTE NEEDS AN UPDATE')).toBeVisible()
  await expect(page.locator('.map')).toHaveAttribute('data-route-state', 'clear')
  const noStairs = await routeAndReadRequest(page)
  expect(noStairs.request.profile).toBe('avoid_mapped_stairs')
  await page.screenshot({ path: `${screenshotDir}/round2-route-avoid-stairs.png` })
  await page.getByRole('button', { name: /Shortest route/ }).click()
  const standard = await routeAndReadRequest(page)
  expect(standard.request.profile).toBe('standard')

  await page.getByRole('button', { name: /Prefer documented paths/ }).click()
  await expect(page.getByText('ROUTE NEEDS AN UPDATE')).toBeVisible()
  const documented = await routeAndReadRequest(page)
  expect(documented.request.profile).toBe('prefer_documented_paths')
  expect(documented.body.accessibility).toBeTruthy()
  expect(documented.body.optimization_cost_m).toBeGreaterThanOrEqual(documented.body.distance_m - 1)

  await page.getByRole('button', { name: 'Change', exact: true }).click()
  await chooseRealStop(page, 'San Jose Diridon (Bay 7)')
  await expect(page.locator('.route-result')).toContainText('ROUTE NEEDS AN UPDATE')
  const changedStop = await routeAndReadRequest(page)
  expect(changedStop.request.destination_stop_id).toBe('2936')

  await page.getByRole('button', { name: 'Reset' }).click()
  await expect(page.locator('.map-marker-origin')).toHaveCount(0)
  await expect(page.locator('.map-marker-destination')).toHaveCount(0)
  await expect(page.locator('.route-result')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Find Route' })).toBeDisabled()
  expect(diagnostics.pageErrors).toEqual([])
  expect(diagnostics.consoleErrors).toEqual([])
  expect(diagnostics.apiFailures).toEqual([])
})

test('route comparison reports each objective as available or unavailable', async ({ request }) => {
  const response = await request.post('http://127.0.0.1:8000/route/compare', { data: {
    origin_latitude: 37.32875,
    origin_longitude: -121.90442,
    destination_stop_id: '4514',
  } })
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.algorithm).toBe('astar')
  expect(body.results.map((item: { profile: string }) => item.profile)).toEqual([
    'standard', 'avoid_mapped_stairs', 'prefer_documented_paths',
  ])
  for (const item of body.results) {
    if (item.available) {
      expect(item.route.distance_m).toBeGreaterThan(0)
      expect(item.route.optimization_cost_m).toBeGreaterThanOrEqual(0)
      expect(item.error).toBeNull()
    } else {
      expect(item.route).toBeNull()
      expect(item.error).toBeTruthy()
    }
  }
})

test('location denial, out-of-area selection, and route-service failure recover clearly', async ({ page, context }) => {
  await openApp(page)
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition: (_success: unknown, error: (value: { code: number }) => void) => error({ code: 1 }) },
    })
  })
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.getByRole('alert')).toContainText('Location access was denied')

  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 37.8, longitude: -122.4 })
  await page.reload()
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible()
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.getByRole('alert')).toContainText(/outside the supported .* area/)
  await expect(page.locator('.map-marker-origin')).toHaveCount(0)

  await context.setGeolocation({ latitude: 37.32875, longitude: -121.90442 })
  await page.getByRole('button', { name: 'Use my location' }).click()
  await chooseRealStop(page, 'San Jose Diridon (Bay 11)')
  await page.route('**/route', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Temporary routing service outage.' }) }))
  await page.getByRole('button', { name: 'Find Route' }).click()
  await expect(page.getByRole('alert')).toContainText('Temporary routing service outage')
  await page.unroute('**/route')
  await routeAndReadRequest(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('mobile route sheet stays reachable and the map remains usable', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 37.32875, longitude: -121.90442 })
  await openApp(page)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await expect(page.getByRole('button', { name: 'Find Route' })).toBeVisible()
  await page.screenshot({ path: `${screenshotDir}/final-mobile-initial.png` })
  await page.getByRole('button', { name: 'Collapse route planner' }).click()
  await expect(page.locator('.panel')).toHaveClass(/panel-collapsed/)
  await page.getByRole('button', { name: 'Expand route planner' }).click()
  await expect(page.locator('.panel')).toHaveClass(/panel-expanded/)

  await page.getByRole('button', { name: 'Use my location' }).click()
  await chooseRealStop(page, 'San Jose Diridon (Bay 11)')
  await routeAndReadRequest(page)
  await page.screenshot({ path: `${screenshotDir}/final-mobile-route.png` })
  await page.locator('.route-result').scrollIntoViewIfNeeded()
  await expect(page.locator('.route-result')).toBeVisible()
  await page.screenshot({ path: `${screenshotDir}/final-mobile-route-details.png` })
  await page.setViewportSize({ width: 768, height: 1024 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768)
  await page.screenshot({ path: `${screenshotDir}/final-tablet-route.png` })
})

test('a temporary stop-data outage can be retried without refreshing', async ({ page }) => {
  let failedOnce = false
  await page.route('**/stops', async (route) => {
    if (!failedOnce) {
      failedOnce = true
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Temporary stop-data outage.' }) })
      return
    }
    await route.continue()
  })
  await page.goto('/app', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('alert')).toContainText('Temporary stop-data outage')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible()
  await expect(page.locator('.dataset-status.is-ready')).toContainText(/stops/)
})

test('GroundTruth uses live API evidence and saves a map-selected unverified report', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openApp(page)
  const sourcesResponse = await request.get('http://127.0.0.1:8000/data-sources')
  const candidatesResponse = await request.get('http://127.0.0.1:8000/accessibility/priorities?limit=80')
  expect(sourcesResponse.status()).toBe(200)
  expect(candidatesResponse.status()).toBe(200)
  const sourceData = await sourcesResponse.json()
  const candidates = await candidatesResponse.json()
  expect(sourceData.sources.some((item: { id: string }) => item.id === 'city-sidewalks')).toBe(true)
  expect(candidates.weights.route_impact).toBeGreaterThan(0)

  const groundtruth = page.locator('.groundtruth-panel')
  await groundtruth.scrollIntoViewIfNeeded()
  await expect(groundtruth.getByRole('heading', { name: 'Sidewalk data gaps' })).toBeVisible()
  if (sourceData.sources.find((item: { id: string }) => item.id === 'city-sidewalks')?.feature_count > 0) {
    await groundtruth.getByRole('button', { name: 'Show city sidewalks' }).click()
    await expect.poll(() => page.evaluate(() => (window as Window & { __transitGapMap?: any }).__transitGapMap?.getSource('municipal-sidewalks')?.serialize().data.features.length || 0)).toBeGreaterThan(0)
  }
  if (candidates.candidates.length > 0) {
    await groundtruth.getByRole('button', { name: /nearby VTA stops/ }).first().click()
    await expect(groundtruth.getByText('Evidence detail')).toBeVisible()
    await expect(groundtruth.getByText(/not proof|proximity/i).first()).toBeVisible()
  }

  await groundtruth.getByRole('button', { name: 'Place report pin on map' }).click()
  await expect(page.locator('.map-selection-banner')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.map-selection-banner')).toHaveCount(0)
  await page.locator('.maplibregl-canvas').click({ position: { x: 850, y: 460 } })
  await expect(page.getByLabel('Latitude')).toHaveValue('')

  await groundtruth.getByRole('button', { name: 'Place report pin on map' }).click()
  await expect(page.locator('.map-selection-banner')).toContainText('report location')
  await page.locator('.maplibregl-canvas').click({ position: { x: 850, y: 460 } })
  await expect(page.getByLabel('Latitude')).not.toHaveValue('')
  await page.getByLabel('Observation').selectOption('sidewalk_condition_issue')
  const description = `Playwright test report ${Date.now()}`
  await page.getByLabel(/Details/).fill(description)
  const createResponse = page.waitForResponse((response) => response.url().endsWith('/accessibility/observations') && response.request().method() === 'POST')
  await groundtruth.getByRole('button', { name: 'Submit report' }).click()
  expect((await createResponse).status()).toBe(201)
  await expect(groundtruth.getByRole('status').filter({ hasText: 'unverified community evidence' })).toBeVisible()
  await expect(groundtruth.getByText(description)).toBeVisible()
  await page.goto('/app')
  await expect(page.locator('.dataset-status.is-ready')).toBeVisible({ timeout: 20_000 })
  await groundtruth.scrollIntoViewIfNeeded()
  await expect(groundtruth.getByText(description)).toBeVisible()
})
