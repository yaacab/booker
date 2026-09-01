import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const API_BASE = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";
const DEMO_PASSWORD = "password1";
const TOKEN_CACHE = path.resolve(__dirname, ".demo-tokens.json");

const DEMO_EMAILS = [
  "customer@booker.test",
  "artist@booker.test",
  "venue@booker.test",
] as const;

async function loginDemo(email: string): Promise<{ token: string; user_id: string }> {
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password: DEMO_PASSWORD }),
    });
    if (res.status === 429 && attempt < 7) {
      await new Promise((r) => setTimeout(r, 3000 * (attempt + 1)));
      continue;
    }
    if (!res.ok) {
      throw new Error(`globalSetup login ${email}: ${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<{ token: string; user_id: string }>;
  }
  throw new Error(`globalSetup login ${email} exhausted retries`);
}

export default async function globalSetup() {
  const apiDir = path.resolve(__dirname, "../../api");
  const venvPython = path.resolve(apiDir, "../../.venv/bin/python");
  execSync(`${venvPython} -m booker_api.seed`, {
    cwd: apiDir,
    stdio: "inherit",
  });

  const tokens: Record<string, { token: string; user_id: string }> = {};
  for (const email of DEMO_EMAILS) {
    tokens[email] = await loginDemo(email);
  }
  fs.writeFileSync(TOKEN_CACHE, JSON.stringify(tokens));
}
