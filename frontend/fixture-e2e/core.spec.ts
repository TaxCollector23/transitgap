import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('synthetic CI fixture: keyboard route, profile changes, voice fallback and durable report',async({page,request})=>{
 const health=await request.get('http://127.0.0.1:8001/health');
 expect(health.ok()).toBeTruthy();expect((await health.json()).reports_enabled).toBe(true);
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aAl8AAAAASUVORK5CYII=','base64')}));
 await page.goto('/app');
 await expect(page.locator('.maplibregl-canvas')).toBeVisible();
 await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
 await page.getByText('Enter coordinates instead',{exact:true}).click();
 await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
 await page.getByRole('button',{name:'Use coordinates',exact:true}).focus();await page.keyboard.press('Enter');
 await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
 await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
 const distances=[];
 const labels={standard:'Walking',wheelchair:'Wheelchair',stroller:'Stroller',low_vision:'Low vision'};
 for(const profile of ['standard','wheelchair','stroller','low_vision'] as const){
  const pending=page.waitForResponse(r=>r.url().endsWith('/route')&&r.request().method()==='POST');
  if(profile==='standard'){await page.getByRole('radio',{name:labels[profile],exact:true}).check();await page.getByRole('button',{name:'Find route',exact:true}).focus();await page.keyboard.press('Enter');}
  else await page.getByRole('radio',{name:labels[profile],exact:true}).check();
  const response=await pending;expect(response.request().postDataJSON().profile).toBe(profile);expect(response.status()).toBe(200);distances.push((await response.json()).distance_m);
  await expect(page.locator('.route-headline')).toContainText(labels[profile]);
 }
 expect(distances[1]).toBeGreaterThan(distances[0]);
 await page.getByRole('button',{name:'Read directions aloud',exact:true}).click();
 if(await page.getByRole('button',{name:'Stop reading',exact:true}).isVisible())await page.getByRole('button',{name:'Stop reading',exact:true}).click();
 else await expect(page.getByText(/No local voice|isn't supported/)).toBeVisible();
 await page.getByRole('button',{name:'Report an issue',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Report an issue',exact:true})).toBeVisible();
 await page.getByRole('region',{name:'1. Where is the problem?'}).getByText('Enter coordinates instead',{exact:true}).click();
 await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
 await page.getByRole('button',{name:'Use coordinates'}).click();
 await page.getByLabel("2. What's the problem?").selectOption('pedestrian_pothole');
 await page.getByLabel('3. Details (optional)').fill('SYNTHETIC CI persistence check, not a real observation.');
 const saved=page.waitForResponse(r=>r.url().endsWith('/accessibility/observations')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Submit report'}).click();
 const savedResponse=await saved;expect(savedResponse.status()).toBe(201);
 const report=await savedResponse.json();expect(report.review_status).toBe('UNVERIFIED');
 await expect(page.getByText('Report saved as unverified community evidence.')).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'Sidewalk records that need review',exact:true}).click();
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
 await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
 await page.getByRole('button',{name:'Report an issue',exact:true}).click();
 await expect(page.getByText('Community reports are paused in this version. No report will be saved here.')).toBeVisible();
 await expect(page.getByRole('link',{name:'VTA'}).first()).toBeVisible();
 await expect(page.getByRole('link',{name:'San José 311'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Submit report'})).toHaveCount(0);
});

test('report availability that stalls fails visibly within a bounded time',async({page})=>{
 await page.goto('/app');
 await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
 await page.route('**/health',async route=>{
  await new Promise(resolve=>setTimeout(resolve,5500));
  try { await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ready:true,reports_enabled:false})}); } catch {}
 });
 await page.getByRole('button',{name:'Report an issue',exact:true}).click();
 await expect(page.getByText(/Reporting availability couldn't be checked/)).toBeVisible({timeout:7000});
 await expect(page.getByRole('button',{name:'Submit report'})).toHaveCount(0);
 await expect(page.getByText('Checking report availability…')).toHaveCount(0);
 await page.waitForTimeout(1200);
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
 await page.goto('/app');await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
 await page.getByText('Enter coordinates instead',{exact:true}).click();
 await page.getByLabel('Latitude',{exact:true}).fill('37.32875');await page.getByLabel('Longitude',{exact:true}).fill('-121.90442');
 await page.getByRole('button',{name:'Use coordinates'}).click();
 await page.getByRole('combobox',{name:'Where are you going?'}).fill('SYNTHETIC');
 await page.getByRole('option',{name:/SYNTHETIC CI Stop/}).click();
 await page.getByRole('button',{name:'Find route',exact:true}).click();
 await page.getByRole('button',{name:'Read directions aloud',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause reading',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause reading',exact:true}).click();
 await page.getByRole('button',{name:'Resume reading',exact:true}).click();
 await page.getByRole('button',{name:'Stop reading',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).__speechCalls)).toEqual(expect.arrayContaining(['speak','pause','resume','cancel']));
 await expect(page.getByRole('button',{name:'Stop reading',exact:true})).toHaveCount(0);
});

test('source metadata failure does not hide available candidates or report controls',async({page})=>{
 await page.route('**/data-sources',route=>route.abort());
 await page.route('**/accessibility/priorities?*',route=>route.fulfill({json:{candidates:[{
  id:'gap:synthetic-ci',latitude:37.32875,longitude:-121.90442,
  classification:'UNKNOWN_DATA',category:'synthetic_ci',priority_score:1,
  explanation:'Synthetic CI candidate, not a real observation.',affected_vta_stop_count:1,
  missing_information:['width'],matched_distance_m:null,
  provenance:{municipal_source:null,osm_source:{status:'SOURCE_DOCUMENTED'},interpretation:'Synthetic test only.'}
 }]}}));
 await page.goto('/app');await expect(page.locator('main[data-data-state="ready"]')).toBeVisible();
 await page.getByRole('button',{name:'Sidewalk records that need review',exact:true}).click();
 await expect(page.locator('.gap-item').first()).toBeVisible();
 await expect(page.locator('.gap-item').first()).toContainText('Near SYNTHETIC CI Stop');
 await expect(page.locator('.gap-item').first()).toContainText('path width');
 await expect(page.getByRole('button',{name:'Report an issue'}).first()).toBeEnabled();
 await expect(page.getByText('Source metadata is unavailable. Candidate records still include their individual source details.')).toBeVisible();
 await page.locator('.gap-item').first().click();
 await expect(page.getByText('Evidence detail',{exact:true})).toBeVisible();
 await expect(page.locator('.gap-detail')).toContainText('These records are suggestions for inspection, not confirmed barriers.');
 await expect(page.locator('.gap-detail')).not.toContainText('reproducibly sampled graph-origin routes');
 await page.unroute('**/data-sources');
 await page.getByRole('button',{name:'Try loading evidence again'}).click();
 await expect(page.getByText('Source metadata is unavailable. Candidate records still include their individual source details.')).toHaveCount(0);
});
