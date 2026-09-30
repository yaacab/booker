import assert from "node:assert/strict";
import test from "node:test";
import {
  fetchPublicVenueMetadataFacts,
  sitemapUnavailable,
  sitemapXml,
} from "./public-seo.ts";

test("venue metadata fetch bypasses caches and observes an immediate revoke", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const calls: { input: string; init?: RequestInit }[] = [];
  let available = true;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ input: String(input), init });
    if (!available) return new Response("Not found", { status: 404 });
    return Response.json({ name: "Площадка", city: "Москва", address: "Адрес" });
  }) as typeof fetch;

  assert.deepEqual(await fetchPublicVenueMetadataFacts("venue/id"), {
    name: "Площадка",
    city: "Москва",
    address: "Адрес",
  });
  available = false;
  assert.equal(await fetchPublicVenueMetadataFacts("venue/id"), null);
  assert.equal(calls.length, 2);
  assert.ok(calls.every((call) => call.init?.cache === "no-store"));
  assert.ok(calls.every((call) => call.input.endsWith("/venues/venue%2Fid")));
});

test("sitemap responses cannot retain revoked venue URLs", () => {
  const response = sitemapXml(["/venues/visible"]);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.match(response.headers.get("content-type") ?? "", /^application\/xml/);

  const artistOnly = sitemapXml(["/artists/visible"]);
  assert.equal(artistOnly.headers.get("cache-control"), "public, max-age=300");

  const unavailable = sitemapUnavailable();
  assert.equal(unavailable.headers.get("cache-control"), "no-store, max-age=0");
});
