#!/usr/bin/env node
/**
 * Capture G2 role cabinet screenshots (customer / performer / venue × 1440 / 390).
 *
 * Prefer: npm run test:e2e -- e2e/g2-screenshots.spec.ts (from apps/web)
 * This wrapper just forwards to Playwright with the same config (reuses API/web).
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const webDir = path.join(root, "apps/web");
const result = spawnSync(
  path.join(webDir, "node_modules/.bin/playwright"),
  ["test", "e2e/g2-screenshots.spec.ts"],
  { cwd: webDir, stdio: "inherit", env: process.env },
);
process.exit(result.status ?? 1);
