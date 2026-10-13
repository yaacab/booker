#!/usr/bin/env node

import fs from "node:fs/promises";
import process from "node:process";

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const inputPath = argument("--input", "data/moscow_venues_open.json");
const outputPath = argument("--output", "/tmp/moscow_venues_enriched.json");
const concurrency = Math.max(1, Number(argument("--concurrency", "8")));
const checkedAt = new Date().toISOString().slice(0, 10);
const ignoredHosts = new Set([
  "openstreetmap.org",
  "www.openstreetmap.org",
  "wikidata.org",
  "www.wikidata.org",
  "commons.wikimedia.org",
]);
const stopWords = new Set([
  "moscow", "москва", "московский", "московская", "театр", "музей", "центр",
  "клуб", "зал", "дом", "дворец", "галерея", "кинотеатр", "стадион",
  "официальный", "сайт", "имени", "государственный", "городской",
  "культурный", "культуры",
]);
const nonEventPattern = /кладбищ|монастыр|храм|церк|больниц|поликлиник|архив|институт|университет|школа|детский сад/i;
const eventPatterns = [
  ["venue_rental", /аренд[а-я]*\s+(?:зал|площадк|пространств|сцен|павильон)/i],
  ["private_event", /частн[а-я]*\s+мероприят/i],
  ["corporate", /корпоратив/i],
  ["wedding", /свадьб/i],
  ["banquet", /банкет|фуршет/i],
  ["conference", /конференц|презентац/i],
  ["concert_hire", /концертн[а-я]*\s+(?:зал|площадк)|организац[а-я]*\s+концерт/i],
  ["event_space", /event[- ]?(?:space|venue)|ивент[- ]?(?:площадк|пространств)/i],
];

function websiteCandidate(row) {
  for (const value of [row.official_website, row.source_url]) {
    if (!value) continue;
    try {
      const url = new URL(value.includes("://") ? value : "https://" + value);
      if (!ignoredHosts.has(url.hostname.toLowerCase())) return url.href;
    } catch {
      // Invalid values remain in moderation.
    }
  }
  return "";
}

function decode(value) {
  return String(value || "")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/\s+/g, " ")
    .trim();
}

function stripHtml(html) {
  return decode(
    html
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function meta(html, key) {
  const tags = html.match(/<meta\b[^>]*>/gi) || [];
  for (const tag of tags) {
    const lower = tag.toLowerCase();
    const quoted = ['name="' + key + '"', "name='" + key + "'", 'property="' + key + '"', "property='" + key + "'"];
    if (!quoted.some((needle) => lower.includes(needle.toLowerCase()))) continue;
    const content = tag.match(/content\s*=\s*["']([^"']+)["']/i);
    if (content) return decode(content[1]);
  }
  return "";
}

function pageTitle(html) {
  return decode((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || "");
}

function identityTokens(name) {
  const tokens = String(name || "")
    .normalize("NFKC")
    .toLowerCase()
    .replaceAll("ё", "е")
    .match(/[a-zа-я0-9]+/g) || [];
  return tokens.filter((token) => token.length >= 4 && !stopWords.has(token));
}

function identityMatches(row, text) {
  const haystack = text.toLowerCase().replaceAll("ё", "е");
  return identityTokens(row.name).some((token) => haystack.includes(token));
}

function absoluteUrl(value, base) {
  if (!value || value.startsWith("data:")) return "";
  try {
    const url = new URL(value, base);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function contact(html, prefix) {
  const links = html.match(/href\s*=\s*["'][^"']+["']/gi) || [];
  for (const link of links) {
    const value = (link.match(/href\s*=\s*["']([^"']+)["']/i) || [])[1] || "";
    if (value.toLowerCase().startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length).split("?")[0]).trim();
    }
  }
  return "";
}

function priceEvidence(text) {
  const matches = text.match(/[^.!?\n]{0,90}(?:аренд|банкет|минимальн|депозит|стоимост|цен)[^.!?\n]{0,90}(?:от\s*)?\d[\d\s]{2,8}\s*(?:₽|руб(?:\.|лей|ля)?)[^.!?\n]{0,90}/i);
  return decode((matches || [])[0] || "").slice(0, 260);
}

function eventSignals(text) {
  return eventPatterns.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
}

async function fetchHtml(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": "Buker venue research/1.0 (+https://bukergo.ru)",
        accept: "text/html,application/xhtml+xml",
      },
    });
    const type = response.headers.get("content-type") || "";
    if (!response.ok || !type.toLowerCase().includes("html")) {
      return { ok: false, status: response.status, finalUrl: response.url || url };
    }
    const html = (await response.text()).slice(0, 2000000);
    return { ok: true, status: response.status, finalUrl: response.url || url, html };
  } catch (error) {
    return { ok: false, status: null, finalUrl: url, error: String(error && error.message || error) };
  } finally {
    clearTimeout(timeout);
  }
}

function addSource(row, source) {
  const sources = Array.isArray(row.sources) ? [...row.sources] : [];
  const exists = sources.some((item) => item && item.field_name === source.field_name && item.source_url === source.source_url);
  if (!exists) sources.push(source);
  return sources;
}

function addPhoto(row, photo) {
  const photos = Array.isArray(row.photos) ? [...row.photos] : [];
  if (!photos.some((item) => item && item.photo_url === photo.photo_url)) photos.push(photo);
  return photos;
}

async function enrich(row) {
  const website = websiteCandidate(row);
  if (!website) {
    return { ...row, research_checked_at: checkedAt, research_status: "no_official_site_candidate" };
  }
  const page = await fetchHtml(website);
  if (!page.ok) {
    return {
      ...row,
      research_checked_at: checkedAt,
      research_status: "site_unreachable",
      research_http_status: page.status,
    };
  }
  const title = pageTitle(page.html);
  const description = meta(page.html, "description") || meta(page.html, "og:description");
  const visible = stripHtml(page.html).slice(0, 120000);
  const identityText = title + " " + description + " " + visible.slice(0, 12000);
  const classificationText = row.name + " " + description + " " + visible;
  if (nonEventPattern.test(classificationText)) {
    return {
      ...row,
      research_checked_at: checkedAt,
      research_status: "non_event_source",
      research_http_status: page.status,
      research_title: title.slice(0, 300),
    };
  }
  if (!identityMatches(row, identityText)) {
    return {
      ...row,
      research_checked_at: checkedAt,
      research_status: "identity_mismatch",
      research_http_status: page.status,
      research_title: title.slice(0, 300),
    };
  }
  const signals = eventSignals(classificationText);
  if (!signals.length) {
    return {
      ...row,
      research_checked_at: checkedAt,
      research_status: "official_site_no_event_evidence",
      research_http_status: page.status,
      research_title: title.slice(0, 300),
    };
  }
  const finalUrl = page.finalUrl || website;
  const image = absoluteUrl(meta(page.html, "og:image"), finalUrl);
  const pricing = priceEvidence(visible);
  let result = {
    ...row,
    official_website: finalUrl,
    phone: row.phone || contact(page.html, "tel:"),
    email: row.email || contact(page.html, "mailto:"),
    research_checked_at: checkedAt,
    research_status: "official_event_site_matched",
    research_http_status: page.status,
    research_title: title.slice(0, 300),
    research_event_signals: signals,
    research_price_evidence: pricing,
  };
  if ((!row.description || row.description === "Площадка из Wikidata (Москва)") && description.length >= 80) {
    result.description = description.slice(0, 1200);
  }
  result.sources = addSource(result, {
    field_name: "official_website,description,contact",
    source_url: finalUrl,
    source_kind: "official_site",
  });
  if (image) {
    result.photos = addPhoto(result, {
      photo_url: image,
      photo_source_url: finalUrl,
      photo_rights_status: "unknown",
    });
  }
  if (pricing) {
    result.sources = addSource(result, {
      field_name: "pricing_evidence_unreviewed",
      source_url: finalUrl,
      source_kind: "official_site",
    });
  }
  return result;
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const venues = Array.isArray(payload.venues) ? payload.venues : [];
const results = new Array(venues.length);
let cursor = 0;

async function worker() {
  while (true) {
    const index = cursor;
    cursor += 1;
    if (index >= venues.length) return;
    results[index] = await enrich(venues[index]);
  }
}

await Promise.all(Array.from({ length: concurrency }, () => worker()));
const nextPayload = {
  ...payload,
  version: Math.max(3, Number(payload.version || 0)),
  research_checked_at: checkedAt,
  venues: results,
};
await fs.writeFile(outputPath, JSON.stringify(nextPayload, null, 2) + "\n");

const counts = {};
for (const row of results) {
  const key = row.research_status || "unknown";
  counts[key] = (counts[key] || 0) + 1;
}
console.log(JSON.stringify({ inputPath, outputPath, total: results.length, counts }, null, 2));
