import { defineConfig, devices } from "@playwright/test";

const apiUrl = new URL(process.env.BOOKER_API_URL ?? "http://invalid");
const webUrl = new URL(process.env.BOOKER_E2E_WEB_URL ?? "http://invalid");
const databaseUrl = process.env.BOOKER_DATABASE_URL ?? "";
const tokenCache = process.env.BOOKER_E2E_TOKEN_CACHE ?? "";
const uploadDir = process.env.BOOKER_UPLOAD_DIR ?? "";
const nextDistDir = process.env.BOOKER_E2E_NEXT_DIST_DIR ?? "";
const productionBuild = process.env.BOOKER_E2E_WEB_MODE === "production";
const isolatedBuild = /^\.next-e2e-[a-zA-Z0-9_-]+$/.test(nextDistDir)
  || (productionBuild && nextDistDir === ".next");

function isolatedPort(url: URL, defaultPort: string): number {
  const port = Number(url.port);
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" ||
      !Number.isInteger(port) || port < 1024 || port > 65535 || url.port === defaultPort) {
    throw new Error("Support E2E requires a distinct loopback HTTP port");
  }
  return port;
}

const apiPort = isolatedPort(apiUrl, "8000");
const webPort = isolatedPort(webUrl, "3000");
if (apiPort === webPort || !databaseUrl.startsWith("sqlite:////tmp/") ||
    !tokenCache.startsWith("/tmp/") || !uploadDir.startsWith("/tmp/") ||
    !isolatedBuild ||
    process.env.BOOKER_RUNTIME_ENV !== "test" ||
    process.env.BOOKER_ALLOW_DEMO_SEED !== "1" ||
    process.env.BOOKER_CORS_ORIGINS !== webUrl.origin) {
  throw new Error("Support E2E requires isolated test DB, uploads, cache, build, and CORS origin");
}

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  webServer: [
    {
      command: `cd ../api && .venv/bin/python -m uvicorn booker_api.main:app --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiUrl.origin}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: productionBuild
        ? `npm run start -- --hostname 127.0.0.1 --port ${webPort}`
        : `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      url: webUrl.origin,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: apiUrl.origin, BOOKER_INTERNAL_API_URL: apiUrl.origin },
    },
  ],
  use: { baseURL: webUrl.origin, ...devices["Desktop Chrome"] },
});
