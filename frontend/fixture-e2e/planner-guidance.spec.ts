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
