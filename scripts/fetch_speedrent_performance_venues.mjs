#!/usr/bin/env node

/**
 * Build a research/demo dataset of Moscow venues where an artist can perform.
 *
 * SpeedRent is used as a public listing source for factual venue data. Photos
 * remain third-party references with unknown rights and must not pass the
 * production publication gate without permission from the venue/rightsholder.
 */

import fs from "node:fs/promises";
import path from "node:path";

const BASE_URL = "https://www.speedrent.ru";
const DEFAULT_OUTPUT = "data/moscow_performance_venues_research.json";
const CHECKED_AT = new Date().toISOString();
const USER_AGENT =
  "BukerGo venue research/1.0 (+https://bukergo.ru; investor demo dataset)";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}

const outputPath = path.resolve(args.get("--output") || DEFAULT_OUTPUT);
const limit = Math.max(1, Number(args.get("--limit") || 300));
const concurrency = Math.max(1, Number(args.get("--concurrency") || 10));
const maxLoftPages = Math.max(1, Number(args.get("--max-loft-pages") || 35));

const strongPerformancePatterns = [
  ["stage", /\bсцен(?:а|ой|у|ы|е)|подиум/i],
  ["concert", /концерт|жив(?:ая|ой) музык|выступлен/i],
  ["sound", /акустическ(?:ая|ое|ую) систем|звуков(?:ая|ое|ую) оборуд|профессиональн(?:ый|ая) звук/i],
  ["microphone", /микрофон/i],
  ["dj", /\bdj\b|дидже/i],
  ["karaoke", /караоке/i],
  ["dancefloor", /танцпол|танцевальн(?:ая|ый) зал/i],
  ["show_light", /светомузык|светов(?:ая|ое) оборуд|сценическ(?:ий|ое) свет/i],
];

const excludedPatterns = [
  /квартир/i,
  /переговорн/i,
  /кабинет/i,
  /тренинг/i,
  /консультац/i,
  /репетитор/i,
  /йог/i,
  /фитнес/i,
  /детск/i,
  /фотостуди/i,
  /подкаст/i,
];

const categoryPriority = {
  koncertnie_zali: 3,
  tantsevalnie_zali: 2,
  loft: 1,
};

function decodeEntities(value = "") {
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&nbsp;|\u00a0/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&#039;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function textContent(value = "") {
  return decodeEntities(
    value
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>|<\/li>|<\/div>/gi, "\n")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/[ \t]+/g, " ")
    .replace(/\s*\n\s*/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function firstMatch(value, regex, group = 1) {
  const match = value.match(regex);
  return match ? textContent(match[group]) : "";
}

function normalizePhotoUrl(url = "") {
  return decodeEntities(url).replace(/\.jpg\.webp(?=\?|$)/i, ".jpg");
}

async function get(url, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: { "user-agent": USER_AGENT, accept: "text/html,application/xhtml+xml" },
        signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return await response.text();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
    }
  }
  throw lastError;
}

function parseListCards(html, category, page) {
  const starts = [...html.matchAll(/<div\s+\n?\s*data-name="([^"]*)"[\s\S]{0,240}?data-id="(\d+)"[\s\S]{0,500}?class="card">/g)];
  return starts.map((match, index) => {
    const segment = html.slice(match.index, starts[index + 1]?.index || html.length);
    const id = match[2];
    const title = firstMatch(segment, /class="card-title-link"[^>]*>([\s\S]*?)<\/a>/i);
    const priceText = firstMatch(segment, /<span class="price">([\s\S]*?)<\/span>/i);
    const price = Number(priceText.replace(/\D/g, "")) || null;
    const area = Number(firstMatch(segment, /class="option-label">\s*([\d\s]+)\s*м/i).replace(/\D/g, "")) || null;
    const capacity = Number(firstMatch(segment, /class="option-label">\s*([\d\s]+)\s*человек/i).replace(/\D/g, "")) || null;
    const metro = firstMatch(segment, /class="address">([\s\S]*?)<\/div>/i);
    const imageMatches = [...segment.matchAll(/<img[^>]+(?:src|data-src)="(https:\/\/[^"\s]+)"/gi)];
    const photos = [...new Set(imageMatches.map((item) => normalizePhotoUrl(item[1])).filter(Boolean))];
    return {
      id,
      title,
      price,
      area,
      capacity,
      metro,
      photos,
      category,
      page,
      source_url: `${BASE_URL}/venue/${id}`,
      price_source_url: `${BASE_URL}/ajax/spaces?venuetype=${category}&page=${page}`,
    };
  });
}

function performanceSignals(text) {
  return strongPerformancePatterns
    .filter(([, pattern]) => pattern.test(text))
    .map(([name]) => name);
}

function trimOwnerDescription(text) {
  const boundaries = [
    /\n?Условия возврата/i,
    /\n?Правила отмены/i,
    /\n?В начале мероприятия необходимо внести страховой залог/i,
  ];
  let result = text;
  for (const boundary of boundaries) {
    const match = result.match(boundary);
    if (match?.index > 100) result = result.slice(0, match.index);
  }
  return result.replace(/\s+/g, " ").trim();
}

function parseDetail(card, html) {
  const articles = [...html.matchAll(/<article[^>]*>([\s\S]*?)<\/article>/gi)]
    .map((match) => trimOwnerDescription(textContent(match[1])))
    .filter((text) => text.length >= 60)
    .sort((a, b) => b.length - a.length);
  const description = articles[0] || firstMatch(html, /<meta property="og:description" content="([^"]+)"/i);
  const title = firstMatch(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i) || card.title;
  const ogPhoto = firstMatch(html, /<meta property="og:image" content="([^"]+)"/i);
  const gallery = [...html.matchAll(/<img[^>]+(?:src|data-src)="(https:\/\/[^"\s]+)"[^>]*>/gi)]
    .map((match) => normalizePhotoUrl(match[1]))
    .filter((url) => /venue\/photo|venue8\/photo|reveltime\.storage/i.test(url));
  const photos = [...new Set([normalizePhotoUrl(ogPhoto), ...card.photos, ...gallery].filter(Boolean))].slice(0, 8);
  const contactBlock = html.match(/<div class="loft-contacts"[\s\S]*?<\/div>\s*<\/div>/i)?.[0] || "";
  const address = firstMatch(contactBlock, /title="Открыть в Яндекс Картах"[^>]*>([\s\S]*?)<\/a>/i)
    .replace(/^Открыть в Яндекс Картах\s*/i, "")
    .trim();
  const phoneMatch = html.match(/href="tel:([^"?]+)"/i);
  const phone = phoneMatch ? decodeEntities(phoneMatch[1]).trim() : "";
  const optionLabels = [...html.matchAll(/class="option-label">([\s\S]*?)<\/div>/gi)]
    .map((match) => textContent(match[1]))
    .filter((text) => text && !/^\d+\s*(?:м|человек)/i.test(text));
  const evidenceText = [title, description, ...optionLabels].join(" ");
  const signals = performanceSignals(evidenceText);
  if (card.category === "koncertnie_zali") signals.unshift("concert_hall_category");
  if (card.category === "tantsevalnie_zali") signals.unshift("dance_hall_category");
  const excluded = excludedPatterns.some((pattern) => pattern.test(title));
  const categoryQualified = card.category === "koncertnie_zali" || card.category === "tantsevalnie_zali";
  const qualifies = !excluded && Boolean(card.price && photos.length && description.length >= 80) && (categoryQualified || signals.length >= 2);
  return { ...card, title, description, address, phone, photos, optionLabels, signals, qualifies };
}

async function mapConcurrent(items, worker, poolSize) {
  const results = new Array(items.length);
  let cursor = 0;
  async function run() {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      try {
        results[index] = await worker(items[index], index);
      } catch (error) {
        results[index] = { ...items[index], error: String(error), qualifies: false };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(poolSize, items.length) }, run));
  return results;
}

async function collectListCategory(category, maxPages) {
  const firstUrl = `${BASE_URL}/ajax/spaces?venuetype=${category}&page=1`;
  const firstHtml = await get(firstUrl);
  const total = Number((firstHtml.match(/из\s+([\d\s]+)\s+предложений/i)?.[1] || "0").replace(/\D/g, ""));
  const pages = Math.min(maxPages, Math.max(1, Math.ceil(total / 24)));
  const pageNumbers = Array.from({ length: pages }, (_, index) => index + 1);
  const pageHtml = await mapConcurrent(
    pageNumbers,
    async (page) => (page === 1 ? firstHtml : await get(`${BASE_URL}/ajax/spaces?venuetype=${category}&page=${page}`)),
    Math.min(concurrency, 8),
  );
  const cards = pageHtml.flatMap((html, index) => parseListCards(html, category, index + 1));
  process.stderr.write(`${category}: ${cards.length} карточек из ${total}\n`);
  return cards;
}

function toVenue(row, rank) {
  const sourceUrl = row.source_url;
  return {
    source_id: `speedrent:${row.id}`,
    rank,
    name: row.title,
    city: "Москва",
    address: row.address,
    metro: row.metro,
    venue_type: row.category === "koncertnie_zali" ? "concert_hall" : row.category === "tantsevalnie_zali" ? "dance_hall" : "event_loft",
    description: row.description,
    capacity: row.capacity,
    area_sqm: row.area,
    tariff_from_rub: row.price,
    tariff_unit: "hour",
    currency: "RUB",
    phone: row.phone,
    event_contact: row.phone,
    has_stage: row.signals.includes("stage"),
    has_sound: row.signals.some((signal) => ["sound", "microphone", "dj", "karaoke"].includes(signal)),
    has_light: row.signals.includes("show_light"),
    performance_evidence: row.signals,
    official_website: "",
    source_url: sourceUrl,
    attribution: "SpeedRent — публичная карточка площадки",
    research_status: "investor_demo_verified_listing",
    research_checked_at: CHECKED_AT,
    photos: row.photos.slice(0, 5).map((photoUrl, index) => ({
      photo_url: photoUrl,
      photo_source_url: sourceUrl,
      photo_rights_status: "unknown",
      usage_scope: "investor_demo_reference_only",
      attribution: `Фото из карточки SpeedRent, фото ${index + 1}`,
    })),
    sources: [
      {
        field_name: "name,address,description,capacity,equipment,contact",
        source_url: sourceUrl,
        source_kind: "specialized_marketplace_listing",
        checked_at: CHECKED_AT,
      },
      {
        field_name: "tariff_from_rub,tariff_unit",
        source_url: row.price_source_url,
        source_kind: "specialized_marketplace_search_price",
        checked_at: CHECKED_AT,
      },
    ],
  };
}

async function main() {
  const concertCards = await collectListCategory("koncertnie_zali", 20);
  const loftCards = await collectListCategory("loft", maxLoftPages);
  const danceCards = await collectListCategory("tantsevalnie_zali", 12);
  const unique = new Map();
  for (const card of [...concertCards, ...loftCards, ...danceCards]) {
    const current = unique.get(card.id);
    if (!current || categoryPriority[card.category] > categoryPriority[current.category]) {
      unique.set(card.id, card);
    }
  }

  process.stderr.write(`Проверяю ${unique.size} полных карточек…\n`);
  const detailed = await mapConcurrent(
    [...unique.values()],
    async (card) => parseDetail(card, await get(card.source_url)),
    concurrency,
  );
  const qualified = detailed
    .filter((row) => row.qualifies)
    .sort((a, b) => {
      const categoryScore = (value) => categoryPriority[value] || 0;
      return categoryScore(b.category) - categoryScore(a.category) || b.signals.length - a.signals.length || (b.capacity || 0) - (a.capacity || 0);
    })
    .slice(0, limit)
    .map((row, index) => toVenue(row, index + 1));

  const payload = {
    version: 1,
    batch_id: `moscow-performance-research-${CHECKED_AT.slice(0, 10)}`,
    generated_at: CHECKED_AT,
    city: "Москва",
    purpose: "Private investor demo research dataset; not automatically public catalog content",
    publication_note: "Third-party photo references require rights clearance before public publication.",
    source_registry: [
      {
        name: "SpeedRent",
        url: `${BASE_URL}/spaces/city-moscow`,
        role: "Primary facts, hourly list price and external photo references",
      },
      {
        name: "LOFT HALL",
        url: "https://lofthall.ru/",
        role: "Official operator cross-check for its Moscow halls and performance capabilities",
      },
      {
        name: "EventCatalog",
        url: "https://eventcatalog.ru/area",
        role: "Independent specialization/address cross-check and discovery queue",
      },
    ],
    selection: {
      requested: limit,
      selected: qualified.length,
      rules: [
        "Moscow listing with a numeric public rental price",
        "At least one real external photo reference",
        "Owner/listing description of at least 80 characters",
        "Concert or dance category, or at least two explicit performance-equipment signals",
        "Residential, meeting-room, podcast and photo-studio-only listings excluded",
      ],
    },
    venues: qualified,
  };

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  process.stderr.write(`Готово: ${qualified.length} площадок → ${outputPath}\n`);
  if (qualified.length < limit) process.exitCode = 2;
}

await main();
