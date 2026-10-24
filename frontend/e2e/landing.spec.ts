import { test, expect } from '@playwright/test';

test('city hero and editorial page work at all five target sizes', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  const broken: string[] = [];
  page.on('response', r => { if(r.status() >= 400 && /\.(webp|png|woff2?)(\?|$)/.test(r.url())) broken.push(r.url()); });
  for (const [width, height] of [[375,812],[390,844],[768,1024],[1440,900],[1920,1080]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    await page.locator(".landing-art").evaluate((image: HTMLImageElement) => image.decode());
    await expect(page.getByRole('heading', {name:'A city for all.',exact:true})).toBeVisible();
    await expect(page.locator('.landing-actions a')).toHaveCount(2);
    const state = await page.evaluate(() => {
      const hero = document.querySelector('.landing-hero')!;
      const art = document.querySelector<HTMLImageElement>('.landing-art')!;
      const editorial = document.querySelector('.landing-editorial')!;
      return { height:hero.getBoundingClientRect().height, art:art.getBoundingClientRect().bottom,
        loaded:art.complete && art.naturalWidth > 758,
        font:getComputedStyle(hero).fontFamily, white:getComputedStyle(editorial).backgroundColor,
        black:[...document.querySelectorAll('.landing h1,.landing h2,.landing h3,.landing p')].every(e=>getComputedStyle(e).color==='rgb(0, 0, 0)'),
        overflow:document.documentElement.scrollWidth > innerWidth };
    });
    expect(state).toMatchObject({ height, art:height, loaded:true, white:'rgb(255, 255, 255)', black:true, overflow:false });
    expect(state.font).toContain('DM Sans');
    await expect(page.locator('.network-preview,.landing-eyebrow,.eyebrow,.badge,.pill')).toHaveCount(0);
    await expect(page.locator('.landing img:not(.landing-art)')).toHaveCount(0);
    await page.getByRole('link', {name:'How TransitGap works',exact:true}).click();
    await expect.poll(async()=> (await page.locator('#how-it-works').evaluate(e=>Math.abs(e.getBoundingClientRect().top-32))) < 2).toBe(true);
    await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Data & methods'}).click();
    await expect(page).toHaveURL(/#methodology$/);
    await page.locator('.landing-footer').scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>scrollY)).toBeGreaterThan(height);
    await page.screenshot({path:`test-artifacts/screenshots/final-landing-${width}.png`,fullPage:true});
  }
  await page.goto('/');
  await page.getByRole('link',{name:'Explore the map',exact:true}).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({timeout:30000});
  await page.reload();
  await expect(page.locator('main[data-data-state="ready"]')).toBeVisible({timeout:30000});
  await page.goBack();
  await expect(page.getByRole('heading',{name:'A city for all.',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
  expect(broken).toEqual([]);
});

test('landing keyboard navigation and reduced motion remain accessible', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'Skip introduction'})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#why-transitgap$/);
  expect(await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
});
