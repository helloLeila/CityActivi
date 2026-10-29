#!/usr/bin/env node
/**
 * Copy one verified GBA tech-events batch into the CityActivi inbox and import it.
 *
 * Usage:
 *   node scripts/sync-gba-events-to-cityactivi.mjs /path/to/2026-10-27-gba-tech-events.json
 *
 * The destination is intentionally fixed by the daily-search contract. Existing
 * batches are never overwritten; a -v2/-v3 suffix is selected automatically.
 */

import { existsSync, mkdirSync, copyFileSync } from "node:fs";
import { basename, dirname, extname, join, resolve } from "node:path";
import { execFileSync } from "node:child_process";

const CITYACTIVI_ROOT = "/Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df";
const INBOX = join(CITYACTIVI_ROOT, "data", "event-inbox");

function fail(message) {
  console.error(`CityActivi sync failed: ${message}`);
  process.exit(2);
}

const source = process.argv[2] && resolve(process.argv[2]);
if (!source || !existsSync(source)) fail("JSON batch path is missing or does not exist");
if (extname(source).toLowerCase() !== ".json") fail("input must be a .json batch file");

mkdirSync(INBOX, { recursive: true });
// Keep the batch date from the input, but avoid stacking version suffixes
// when a prior manual test is passed back into the script (v2-v2, v2-v2-v2).
const sourceName = basename(source, ".json").replace(/-v\d+$/, "");
let destination = join(INBOX, `${sourceName}.json`);
let version = 1;
while (existsSync(destination)) {
  version += 1;
  destination = join(INBOX, `${sourceName}-v${version}.json`);
}
copyFileSync(source, destination);
console.log(`Copied ${source} -> ${destination}`);

function runningWorker() {
  try {
    const output = execFileSync("docker", ["compose", "ps", "--status", "running", "-q", "worker"], {
      cwd: CITYACTIVI_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    return output.length > 0;
  } catch {
    return false;
  }
}

if (runningWorker()) {
  execFileSync("docker", ["compose", "exec", "-T", "worker", "python", "-m", "backend.app.import_events", "--inbox", "/app/data/event-inbox"], {
    cwd: CITYACTIVI_ROOT,
    stdio: "inherit",
  });
  console.log("CityActivi import completed via Docker worker.");
} else {
  const python = join(CITYACTIVI_ROOT, ".venv", "bin", "python");
  if (!existsSync(python)) fail(`local interpreter not found: ${python}`);
  execFileSync(python, ["-m", "backend.app.import_events", "--inbox", "data/event-inbox"], {
    cwd: CITYACTIVI_ROOT,
    stdio: "inherit",
  });
  console.log("CityActivi import completed via local worker command.");
}
