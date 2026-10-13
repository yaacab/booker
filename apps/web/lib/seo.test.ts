import assert from "node:assert/strict";
import test from "node:test";
import {
  INDEXABLE_STATIC_PATHS,
  canonicalSiteUrl,
  publicProfilePath,
} from "./seo";

test("SEO allowlist excludes private and transactional routes", () => {
  assert.deepEqual(
    INDEXABLE_STATIC_PATHS.filter((path) =>
      ["/login", "/events/new", "/cabinet", "/investor/venues"].includes(path),
    ),
    [],
  );
  assert.ok(INDEXABLE_STATIC_PATHS.includes("/"));
  assert.ok(INDEXABLE_STATIC_PATHS.includes("/search"));
  assert.ok(INDEXABLE_STATIC_PATHS.includes("/legal/privacy"));
});

test("canonical URL and public profile paths are normalized", () => {
  assert.equal(canonicalSiteUrl("https://bukergo.ru///"), "https://bukergo.ru");
  assert.equal(publicProfilePath("artist", "artist id"), "/artists/artist%20id");
  assert.equal(publicProfilePath("venue", "venue/id"), "/venues/venue%2Fid");
});
