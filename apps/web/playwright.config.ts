import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API_URL = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";
const WEB_URL = process.env.BOOKER_WEB_URL ?? "http://127.0.0.1:3000";
const API_PORT = Number(new URL(API_URL).port || 8000);
const WEB_PORT = Number(new URL(WEB_URL).port || 3000);
const repoPython = path.resolve(__dirname, "../../.venv/bin/python");
const configuredPython = process.env.BOOKER_PYTHON_BIN;
if (configuredPython && !/^[A-Za-z0-9_./-]+$/.test(configuredPython)) {
  throw new Error("BOOKER_PYTHON_BIN must be a plain executable path");
}
const pythonBin =
  configuredPython ??
  (fs.existsSync(repoPython) ? "../../.venv/bin/python" : "python3");

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  webServer: [
    {
      command: `cd ../api && BOOKER_ENVIRONMENT=test BOOKER_PAYMENT_PROVIDER=stub BOOKER_PAYMENT_ALLOW_STUB=true BOOKER_TEST_AUTH_RATE_LIMIT=1000 ${pythonBin} -m uvicorn booker_api.main:app --host 127.0.0.1 --port ${API_PORT}`,
      url: `${API_URL}/health`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: `NEXT_PUBLIC_API_URL=${API_URL} npm run dev -- --port ${WEB_PORT}`,
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
  use: { baseURL: WEB_URL, ...devices["Desktop Chrome"] },
});
