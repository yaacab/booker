import assert from "node:assert/strict";
import test from "node:test";
import {
  PROMO_UTM_SOURCE,
  buildShareUrl,
  parsePromoAttribution,
  profilePath,
  qrCodeImageUrl,
} from "./promo.ts";

test("buildShareUrl adds canonical UTM without PII", () => {
  const prev = process.env.NEXT_PUBLIC_SITE_URL;
  process.env.NEXT_PUBLIC_SITE_URL = "https://bukergo.ru";
  const url = buildShareUrl("artist", "abc-123", { medium: "qr" });
  assert.match(url, /^https:\/\/bukergo\.ru\/artists\/abc-123\?/);
  const params = new URL(url).searchParams;
  assert.equal(params.get("utm_source"), PROMO_UTM_SOURCE);
  assert.equal(params.get("utm_medium"), "qr");
  assert.equal(params.get("utm_campaign"), "artist_profile");
  assert.equal(params.get("email"), null);
  if (prev === undefined) delete process.env.NEXT_PUBLIC_SITE_URL;
  else process.env.NEXT_PUBLIC_SITE_URL = prev;
});

test("buildShareUrl supports venue hall deep link", () => {
  const prev = process.env.NEXT_PUBLIC_SITE_URL;
  process.env.NEXT_PUBLIC_SITE_URL = "https://bukergo.ru";
  const url = buildShareUrl("venue", "v1", { medium: "social", hallId: "hall-9" });
  const params = new URL(url).searchParams;
  assert.equal(params.get("utm_campaign"), "venue_profile");
  assert.equal(params.get("hall"), "hall-9");
  if (prev === undefined) delete process.env.NEXT_PUBLIC_SITE_URL;
  else process.env.NEXT_PUBLIC_SITE_URL = prev;
});

test("parsePromoAttribution ignores non-promo traffic", () => {
  assert.equal(parsePromoAttribution("utm_source=google"), null);
  assert.equal(parsePromoAttribution(""), null);
});

test("parsePromoAttribution reads booker_share params", () => {
  const parsed = parsePromoAttribution(
    `utm_source=${PROMO_UTM_SOURCE}&utm_medium=link&utm_campaign=artist_profile&tariff=t1`,
  );
  assert.ok(parsed);
  assert.equal(parsed!.medium, "link");
  assert.equal(parsed!.tariffId, "t1");
});

test("profilePath encodes id", () => {
  assert.equal(profilePath("venue", "a/b"), "/venues/a%2Fb");
});

test("qrCodeImageUrl encodes payload", () => {
  const src = qrCodeImageUrl("https://bukergo.ru/artists/x?utm_source=booker_share", 200);
  assert.match(src, /^https:\/\/api\.qrserver\.com\/v1\/create-qr-code\/\?/);
  assert.match(src, /size=200x200/);
  assert.match(src, /data=https%3A%2F%2Fbukergo.ru/);
});
