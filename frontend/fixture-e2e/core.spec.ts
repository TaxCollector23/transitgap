import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('synthetic CI fixture: keyboard route, profile changes, voice fallback and durable report',async({page})=>{
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aAl8AAAAASUVORK5CYII=','base64')}));
 await page.goto('/app');
 await expect(page.locator('.maplibregl-canvas')).toBeVisible();
 await expect(page.locator('.dataset-status.is-ready')).toBeVisible();
 await page.getByText('Search an address',{exact:true}).click();
 await page.getByText('Enter coordinates instead',{exact:true}).click();
 await page.getByLabel('Starting latitude').fill('37.32875');await page.getByLabel('Starting longitude').fill('-121.90442');
 await page.getByRole('button',{name:'Use coordinates',exact:true}).focus();await page.keyboard.press('Enter');
 await page.getByRole('searchbox',{name:'Search VTA stops'}).fill('SYNTHETIC');
 await page.getByRole('button',{name:/SYNTHETIC CI Stop/}).click();
 const distances=[];
 for(const profile of ['standard','wheelchair','stroller','low_vision']){
  await page.locator('#mobility-profile').selectOption(profile);
  const pending=page.waitForResponse(r=>r.url().endsWith('/route')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Find Route',exact:true}).focus();await page.keyboard.press('Enter');
  const response=await pending;expect(response.request().postDataJSON().profile).toBe(profile);expect(response.status()).toBe(200);distances.push((await response.json()).distance_m);
  await expect(page.getByRole('region',{name:'Route details'})).toBeVisible();
 }
 expect(distances[1]).toBeGreaterThan(distances[0]);
 await page.getByRole('button',{name:'Read aloud',exact:true}).click();
 if(await page.getByRole('button',{name:'Stop reading',exact:true}).isVisible())await page.getByRole('button',{name:'Stop reading',exact:true}).click();
 else await expect(page.getByText(/No local voice|isn't supported/)).toBeVisible();
 await page.getByRole('button',{name:'Report an issue',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Report an issue',exact:true})).toBeVisible();
 await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
 await page.getByLabel('Observation',{exact:true}).selectOption('pedestrian_pothole');
 await page.getByLabel('Details optional').fill('SYNTHETIC CI persistence check, not a real observation.');
 await page.getByRole('button',{name:'Submit report'}).click();
 await expect(page.getByText('Report saved as unverified community evidence.')).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'Evidence',exact:true}).click();
 await expect(page.getByText('SYNTHETIC CI persistence check, not a real observation.').first()).toBeVisible();
 const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();expect(axe.violations.map(v=>v.id)).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
