import { defineConfig, devices } from "@playwright/test";

const API_URL = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  webServer: [
    {
      command: "cd ../api && ../../.venv/bin/python -m uvicorn booker_api.main:app --host 127.0.0.1 --port 8000",
      url: `${API_URL}/health`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: `NEXT_PUBLIC_API_URL=${API_URL} npm run dev`,
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
  use: { baseURL: "http://127.0.0.1:3000", ...devices["Desktop Chrome"] },
});
