import { readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const excluded = new Set(["node_modules", "e2e", "playwright-report", "test-results"]);

function discover(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || excluded.has(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...discover(path));
    else if (entry.isFile() && /\.test\.(?:[cm]?[jt]s|tsx|jsx)$/.test(entry.name)) files.push(path);
  }
  return files;
}

// Новые unit-тесты попадают в CI автоматически, без отдельного ручного списка.
const files = discover(root).sort().map((path) => relative(root, path));
if (!files.length) throw new Error("No unit test files found");
console.log(`Unit test files: ${files.length}`);
const result = spawnSync(process.execPath, ["--import", "tsx", "--test", ...files], {
  cwd: root, stdio: "inherit",
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
