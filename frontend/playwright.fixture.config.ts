import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./fixture-e2e',workers:1,timeout:45000,
 use:{baseURL:'http://127.0.0.1:5174',viewport:{width:390,height:844},trace:'retain-on-failure',screenshot:'only-on-failure'},
 outputDir:'test-artifacts/fixture-results',reporter:[['list']],
 webServer:[
 {command:`${process.env.TRANSITGAP_PYTHON || './backend/.venv/bin/python'} -m uvicorn scripts.fixture_server:app --host 127.0.0.1 --port 8001`,cwd:'..',url:'http://127.0.0.1:8001/health',reuseExistingServer:!process.env.CI,timeout:60000},
 {command:'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',url:'http://127.0.0.1:5174',env:{VITE_API_BASE_URL:'http://127.0.0.1:8001'},reuseExistingServer:!process.env.CI}
 ]
});
