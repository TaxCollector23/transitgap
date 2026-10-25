import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

for (const viewport of [{width:390,height:844},{width:768,height:1024},{width:1440,height:900},{width:1920,height:1080}]) {
  test(`next action stays visible and guides a destination-first trip at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.goto('/app');
    await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
    const action = page.locator('.planner-action button');
    await expect(action).toHaveText('Choose a starting point');
    const bounds = await action.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.y + bounds!.height).toBeLessThan(viewport.height);
    await expect(page.locator('.step-current')).toHaveCSS('animation-name','none');

    // Users can choose either point first. Selecting a destination must point
    // back to the missing origin, including keyboard focus and panel scroll.
    await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
    await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
    await expect(page.locator('#origin-title')).toBeFocused();
    await expect(action).toHaveText('Choose a starting point');
    await action.click();
    await expect(page.locator('#origin-title')).toBeFocused();

    await page.getByText('Enter coordinates instead',{exact:true}).click();
    await page.getByLabel('Latitude',{exact:true}).fill('37.32875');
    await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
    await page.getByRole('button',{name:'Use coordinates',exact:true}).click();
    await expect(page.locator('#travel-title')).toBeFocused();
    await expect(action).toHaveText('Find route');
    await page.getByRole('radio',{name:'Wheelchair',exact:true}).check();
      await expect(page.getByRole('button',{name:'Try an example trip near Diridon Station'})).toBeVisible();
    await action.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#route-title')).toBeVisible();
    await expect(page.locator('.route-headline')).toContainText('Wheelchair');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    if (viewport.width === 390) {
      const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
      expect(result.violations.map(v=>v.id)).toEqual([]);
    }
  });
}

test('Data & limits uses plain language and hides model settings under More detail', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/app');
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByRole('button',{name:'Data & limits',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Data & limits'})).toBeVisible();
  await expect(page.getByText(/missing information does not mean a sidewalk or crossing is safe or unsafe/)).toBeVisible();
  const moreDetail=page.locator('.methods-panel details');
  await expect(moreDetail.locator('summary')).toHaveText('More detail');
  await expect(page.getByText(/8-second network-search limit/)).toBeHidden();
  await moreDetail.locator('summary').click();
  await expect(page.getByText(/8-second network-search limit/)).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('new trip keeps a profile, app navigation keeps inputs, and clear resets everything', async ({page}) => {
  await page.goto('/app');
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByText('Enter coordinates instead',{exact:true}).click();
  await page.getByLabel('Latitude',{exact:true}).fill('37.32875');
  await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
  await page.getByRole('button',{name:'Use coordinates',exact:true}).click();
  await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
  await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
  await page.getByRole('radio',{name:'Wheelchair',exact:true}).check();
  await page.getByRole('button',{name:'Report an issue',exact:true}).click();
  await page.getByRole('button',{name:'← Back to route planning'}).click();
  await expect(page.getByRole('button',{name:'Change starting point'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Change destination'})).toBeVisible();
  await expect(page.getByRole('radio',{name:'Wheelchair',exact:true})).toBeChecked();
  await expect(page.getByRole('button',{name:'Try an example trip near Diridon Station'})).toBeVisible();
  await page.getByRole('button',{name:'Clear trip / Start over'}).click();
  await expect(page.getByRole('radio',{name:'Walking',exact:true})).toBeChecked();
  await expect(page.getByRole('button',{name:'Change starting point'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Change destination'})).toHaveCount(0);
  await page.reload();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(page.getByRole('radio',{name:'Walking',exact:true})).toBeChecked();
});

test('the planner states when the loaded transit schedule does not cover today', async ({page}) => {
  await page.route('**/stops/ci-stop', route => route.fulfill({json:{
    agency:'VTA',
    schedule_url:'https://www.vta.org/go/schedules',
    service:{
      schedule_validity:{status:'not_yet_valid',feed_start_date:'20990101',feed_end_date:'20990131'},
      feed_info:[{feed_start_date:'20990101',feed_end_date:'20990131'}],
    },
  }}));
  await page.goto('/app');
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
  await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
  await expect(page.locator('.schedule-notice')).toContainText('01/01/2099 to 01/31/2099');
  await expect(page.locator('.schedule-notice').getByRole('link',{name:'Check VTA'})).toHaveAttribute('href','https://www.vta.org/go/schedules');
});

test('routing failures are actionable, clear on navigation, and do not recommend failed algorithms', async ({page}) => {
  await page.route('**/route', route => route.fulfill({status:422,json:{detail:'Walking-network search exceeded its 8-second limit. Try moving the start to a nearby street entrance or choosing another stop.'}}));
  await page.goto('/app');
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByText('Enter coordinates instead',{exact:true}).click();
  await page.getByLabel('Latitude',{exact:true}).fill('37.32875');
  await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
  await page.getByRole('button',{name:'Use coordinates',exact:true}).click();
  await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
  await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
  await page.getByRole('button',{name:'Find route',exact:true}).click();
  await expect(page.locator('.notice.error')).toContainText('8-second search limit');
  await expect(page.locator('.notice.error')).toContainText('street or sidewalk entrance');
  await expect(page.locator('.notice.error')).not.toContainText('closer stop');
  await page.getByRole('button',{name:'For cities and advocates'}).click();
  await page.getByRole('button',{name:'← Back to route planning'}).click();
  await expect(page.locator('.notice.error')).toHaveCount(0);

  await page.route('**/algorithms/compare', route => route.fulfill({json:{results:['astar','dijkstra','bidirectional_dijkstra','bellman_ford','breadth_first'].map(algorithm=>({algorithm,error:'search limit exceeded'}))}}));
  await page.getByText('Advanced options',{exact:true}).click();
  await page.getByRole('button',{name:'Compare all five algorithms'}).click();
  await expect(page.locator('.benchmark-unavailable')).toContainText('Move the start to a nearby street entrance or choose another stop.');
  await expect(page.locator('.benchmark-unavailable')).not.toContainText('Try A');
});

test('a shared trip URL restores the destination, starting point, and selected profile', async ({page,context}) => {
  await page.goto('/app');
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
  await page.getByText('Enter coordinates instead',{exact:true}).click();
  await page.getByLabel('Latitude',{exact:true}).fill('37.32875');
  await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
  await page.getByRole('button',{name:'Use coordinates',exact:true}).click();
  await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
  await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
  await page.getByRole('radio',{name:'Wheelchair',exact:true}).check();
  await page.getByRole('button',{name:'Find route',exact:true}).click();
  await expect(page.getByRole('heading',{name:/To SYNTHETIC CI Stop/})).toBeVisible();
  await page.getByRole('button',{name:'Copy link to this trip'}).click();
  await expect(page).toHaveURL(/profile=wheelchair/);
  const shared = await context.newPage();
  await shared.goto(page.url());
  await expect(shared.locator('main[data-data-state="ready"]')).toBeVisible();
  await expect(shared.getByRole('button',{name:'Change starting point'})).toBeVisible();
  await expect(shared.getByRole('button',{name:'Change destination'})).toBeVisible();
  await expect(shared.getByRole('radio',{name:'Wheelchair',exact:true})).toBeChecked();
});
