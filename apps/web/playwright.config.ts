import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  webServer: {
    command: "npm run dev",
    port: 3000,
    reuseExistingServer: true,
    timeout: 120_000,
  },
  use: { baseURL: "http://127.0.0.1:3000", ...devices["Desktop Chrome"] },
});
