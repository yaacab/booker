import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:"./e2e",
  testMatch:"readiness.spec.ts",
  workers:1,
  timeout:120_000,
  expect:{timeout:20_000},
  outputDir:"../../outputs/readiness-browser",
  use:{baseURL:process.env.BOOKER_WEB_URL||"http://127.0.0.1:4316",viewport:{width:1440,height:1000},trace:"retain-on-failure",screenshot:"only-on-failure",launchOptions:{executablePath:process.env.BOOKER_BROWSER_EXECUTABLE}},
});
