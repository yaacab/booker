#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const input = path.resolve(process.argv[2] || "data/moscow_performance_venues_research.json");
const online = process.argv.includes("--online");
const payload = JSON.parse(await fs.readFile(input, "utf8"));
const venues = payload.venues || [];
const errors = [];
const prohibited = /тренинг|консультац|переговор|подкаст|фотостуд|квартир|детск|йог|фитнес|кабинет|репетитор/i;

function check(condition, message) {
  if (!condition) errors.push(message);
}

check(venues.length === 300, `expected 300 venues, found ${venues.length}`);
check(new Set(venues.map((venue) => venue.source_id)).size === venues.length, "source_id values are not unique");
check(new Set(venues.map((venue) => venue.name.toLocaleLowerCase("ru"))).size === venues.length, "venue names are not unique");

for (const [index, venue] of venues.entries()) {
  const label = `row ${index + 1} ${venue.name || "(no name)"}`;
  check(Boolean(venue.name), `${label}: missing name`);
  check(Boolean(venue.address), `${label}: missing address`);
  check(String(venue.description || "").length >= 80, `${label}: description is too short`);
  check(Number(venue.capacity) > 0, `${label}: missing capacity`);
  check(Number(venue.tariff_from_rub) > 0, `${label}: missing numeric price`);
  check(venue.tariff_unit === "hour", `${label}: unsupported tariff unit`);
  const sourcePrefix = "https://www.speedrent.ru/venue/";
  const sourceId = String(venue.source_url || "").slice(sourcePrefix.length);
  check(String(venue.source_url || "").startsWith(sourcePrefix) && Number(sourceId) > 0, label + " invalid source URL");
  check(Array.isArray(venue.photos) && venue.photos.length > 0, `${label}: missing photos`);
  check((venue.photos || []).every((photo) => String(photo.photo_url || "").startsWith("https://")), label + " invalid photo URL");
  check((venue.sources || []).some((source) => /tariff_from_rub/.test(source.field_name || "")), `${label}: price has no source`);
  check(Array.isArray(venue.performance_evidence) && venue.performance_evidence.length > 0, `${label}: no performance evidence`);
  check(!prohibited.test(venue.name || ""), `${label}: prohibited non-performance title`);
}

async function mapConcurrent(items, worker, concurrency = 20) {
  let cursor = 0;
  const results = new Array(items.length);
  async function run() {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      results[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: concurrency }, run));
  return results;
}

if (online) {
  const statuses = await mapConcurrent(venues, async (venue) => {
    const url = venue.photos[0].photo_url;
    try {
      const response = await fetch(url, { method: "HEAD", signal: AbortSignal.timeout(20_000) });
      return { name: venue.name, url, status: response.status, type: response.headers.get("content-type") || "" };
    } catch (error) {
      return { name: venue.name, url, status: 0, type: "", error: String(error) };
    }
  });
  for (const item of statuses) {
    check(item.status >= 200 && item.status < 400, `${item.name}: photo HTTP ${item.status}`);
    check(item.type.startsWith("image/"), `${item.name}: photo is not an image (${item.type})`);
  }
}

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}

const prices = venues.map((venue) => venue.tariff_from_rub);
console.log(JSON.stringify({
  valid: true,
  venues: venues.length,
  unique_sources: new Set(venues.map((venue) => venue.source_id)).size,
  descriptions: venues.filter((venue) => venue.description.length >= 80).length,
  priced: venues.filter((venue) => venue.tariff_from_rub > 0).length,
  photographed: venues.filter((venue) => venue.photos.length > 0).length,
  online_photos_checked: online ? venues.length : 0,
  min_price_rub_per_hour: Math.min(...prices),
  max_price_rub_per_hour: Math.max(...prices),
}, null, 2));
