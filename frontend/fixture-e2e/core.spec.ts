import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('synthetic CI fixture: keyboard route, profile changes, voice fallback and durable report',async({page,request})=>{
 const health=await request.get('http://127.0.0.1:8001/health');
 expect(health.ok()).toBeTruthy();expect((await health.json()).reports_enabled).toBe(true);
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
 await expect(page.getByLabel('Observation',{exact:true})).toBeEnabled();
 await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
 await page.getByLabel('Observation',{exact:true}).selectOption('pedestrian_pothole');
 await page.getByLabel('Details optional').fill('SYNTHETIC CI persistence check, not a real observation.');
 const saved=page.waitForResponse(r=>r.url().endsWith('/accessibility/observations')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Submit report'}).click();
 const savedResponse=await saved;expect(savedResponse.status()).toBe(201);
 const report=await savedResponse.json();expect(report.review_status).toBe('UNVERIFIED');
 await expect(page.getByText('Report saved as unverified community evidence.')).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'Evidence',exact:true}).click();
 await expect(page.getByText('SYNTHETIC CI persistence check, not a real observation.').first()).toBeVisible();
 const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();expect(axe.violations.map(v=>v.id)).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('reporting disabled is explicit and never offers a submit form',async({page})=>{
 await page.route('**/health',async route=>{
  const response=await route.fetch();const body=await response.json();
  await route.fulfill({response,json:{...body,reports_enabled:false}});
 });
 await page.goto('/app');
 await expect(page.locator('.dataset-status.is-ready')).toBeVisible();
 await page.getByRole('button',{name:'Report an issue',exact:true}).click();
 await expect(page.getByText('Public reporting is paused until durable storage is connected. No report will be saved here.')).toBeVisible();
 await expect(page.getByRole('button',{name:'Submit report'})).toHaveCount(0);
});

test('local speech controls pause, resume and stop',async({page})=>{
 await page.addInitScript(()=>{
  const calls:string[]=[];(window as any).__speechCalls=calls;
  const voice={localService:true,lang:'en-US',voiceURI:'test-local',name:'Synthetic local voice',default:true};
  Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{
   getVoices:()=>[voice],addEventListener:()=>{},removeEventListener:()=>{},
   speak:()=>calls.push('speak'),cancel:()=>calls.push('cancel'),pause:()=>calls.push('pause'),resume:()=>calls.push('resume')
  }});
  Object.defineProperty(window,'SpeechSynthesisUtterance',{configurable:true,value:class{constructor(public text:string){}}});
 });
 await page.goto('/app');await expect(page.locator('.dataset-status.is-ready')).toBeVisible();
 await page.getByRole('button',{name:'Read aloud',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause reading',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause reading',exact:true}).click();
 await page.getByRole('button',{name:'Resume reading',exact:true}).click();
 await page.getByRole('button',{name:'Stop reading',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).__speechCalls)).toEqual(expect.arrayContaining(['speak','pause','resume','cancel']));
 await expect(page.getByRole('button',{name:'Stop reading',exact:true})).toHaveCount(0);
});
