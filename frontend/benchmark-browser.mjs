import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
const base = process.env.TRANSITGAP_E2E_URL || 'https://transitgap.vercel.app';
const label = process.env.BENCHMARK_LABEL || 'before';
const folder = `test-artifacts/performance/${label}`;
await fs.mkdir(folder,{recursive:true});
const browser = await chromium.launch();
const reports=[];
for(const [width,height] of [[390,844],[768,1024],[1440,900],[1920,1080]]) {
  const context=await browser.newContext({viewport:{width,height},geolocation:{latitude:37.32875,longitude:-121.90442},permissions:['geolocation']});
  const page=await context.newPage();
  await page.addInitScript(()=>{ window.__transitgapClicks=0; addEventListener('click',()=>{window.__transitgapClicks++;}); });
  const start=Date.now();
  await page.goto(`${base}/app`);
  await page.locator('main[data-data-state="ready"]').waitFor({timeout:90000});
  const plannerMs=Date.now()-start;
  await page.locator('.maplibregl-canvas').waitFor({timeout:60000});
  const canvasMs=Date.now()-start;
  await page.locator('.map[data-map-state="ready"]').waitFor({timeout:60000});
  const mapMs=Date.now()-start;
  await page.screenshot({path:`${folder}/${width}-initial.png`});
  const resources=await page.evaluate(()=>performance.getEntriesByType('resource').filter(e=>/\.js|bootstrap/.test(e.name)).map(e=>({name:e.name.split('/').pop(),duration_ms:Math.round(e.duration),transfer_bytes:e.transferSize,decoded_bytes:e.decodedBodySize})));
  reports.push({width,height,planner_ready_ms:plannerMs,map_canvas_ms:canvasMs,map_ready_ms:mapMs,resources});
  if(!process.env.SKIP_ROUTE) {
    try {
    await page.getByRole('button',{name:'Use my location',exact:true}).click();
    await page.getByRole('button',{name:'Change starting point'}).waitFor();
    const destination=page.getByRole('combobox',{name:'Where are you going?'});
    await destination.click();
    await destination.fill('San Jose Diridon (Bay 11)');
    await page.getByRole('option').filter({hasText:/San Jose Diridon \(Bay 11\)/}).first().click();
    await page.getByRole('button',{name:'Find route',exact:true}).waitFor({state:'visible'});
    await page.getByRole('button',{name:'Find route',exact:true}).click({timeout:90000});
    await page.getByRole('heading',{level:2,name:/^To /}).waitFor({timeout:90000});
    await page.screenshot({path:`${folder}/${width}-route.png`});
    reports.at(-1).walking_pointer_actions=await page.evaluate(()=>window.__transitgapClicks);
    } catch(error) {
      reports.at(-1).route_failure=String(error).slice(0,500);
      await page.screenshot({path:`${folder}/${width}-failure.png`});
    }
  }
  await context.close();
}
await browser.close();
await fs.writeFile(`${folder}/measurements.json`,JSON.stringify({base,label,reports},null,2));
console.log(JSON.stringify(reports,null,2));
