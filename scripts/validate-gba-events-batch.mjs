#!/usr/bin/env node
/** Validate one daily GBA events JSON batch before CityActivi import. */

import { existsSync, readFileSync } from "node:fs";
import { basename, extname, resolve } from "node:path";

function fail(message) {
  console.error(JSON.stringify({ ok: false, error: message }, null, 2));
  process.exit(1);
}

const source = process.argv[2] && resolve(process.argv[2]);
const expectedDate = process.argv[3];
if (!source || !expectedDate || !/^\d{4}-\d{2}-\d{2}$/.test(expectedDate)) {
  fail("usage: validate-gba-events-batch.mjs <json-path> <YYYY-MM-DD>");
}
if (!existsSync(source)) fail(`JSON_NOT_FOUND: ${source}`);
if (extname(source).toLowerCase() !== ".json") fail("INPUT_NOT_JSON");

const filename = basename(source);
const filenameMatch = filename.match(/^(\d{4}-\d{2}-\d{2})-gba-tech-events(?:-v\d+)?\.json$/);
if (!filenameMatch) fail(`INVALID_BATCH_FILENAME: ${filename}`);
if (filenameMatch[1] !== expectedDate) fail(`DATE_FILENAME_MISMATCH: expected ${expectedDate}, got ${filenameMatch[1]}`);

let payload;
try {
  payload = JSON.parse(readFileSync(source, "utf8"));
} catch {
  fail("INVALID_JSON");
}
if (payload.schema_version !== 1) fail("INVALID_SCHEMA_VERSION");
if (payload.producer !== "gba-tech-events") fail("INVALID_PRODUCER");
if (!Array.isArray(payload.events)) fail("EVENTS_NOT_ARRAY");
if (!String(payload.generated_at || "").startsWith(expectedDate)) fail("DATE_GENERATED_AT_MISMATCH");

const requiredFacts = ["title", "timezone", "city", "venue", "organizer", "canonical_url", "technical_signal"];
for (let index = 0; index < payload.events.length; index += 1) {
  const event = payload.events[index];
  const facts = event?.facts;
  if (!facts) fail(`EVENT_${index}_MISSING_FACTS`);
  for (const field of requiredFacts) {
    if (typeof facts[field] !== "string" || !facts[field].trim()) fail(`EVENT_${index}_MISSING_${field}`);
  }
  if (!event.evidence || typeof event.evidence !== "object") fail(`EVENT_${index}_MISSING_EVIDENCE`);
}

console.log(JSON.stringify({ ok: true, file: source, generated_at: payload.generated_at, events: payload.events.length }, null, 2));
