import { defineConfig } from "@playwright/test";

// Exercise the built CSS/chunk loading order without downloading a county graph.
export default defineConfig({
  testDir: "./startup-e2e",
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: process.env.TRANSITGAP_E2E_URL || "http://127.0.0.1:4175",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  outputDir: "test-artifacts/startup-results",
  webServer: process.env.TRANSITGAP_E2E_URL ? undefined : {
    command: "npm run preview -- --host 127.0.0.1 --port 4175 --strictPort",
    url: "http://127.0.0.1:4175",
    reuseExistingServer: false,
  },
});
