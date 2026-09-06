import assert from "node:assert/strict";
import test from "node:test";
import { loginHref, safeNext } from "./next.ts";

test("safeNext allows only internal paths (§5 returnTo)", () => {
  assert.equal(safeNext(null), "/cabinet");
  assert.equal(safeNext("/search?city=Москва"), "/search?city=Москва");
  assert.equal(safeNext("/artists/abc"), "/artists/abc");
  assert.equal(safeNext("//evil.example"), "/cabinet");
  assert.equal(safeNext("https://evil.example"), "/cabinet");
  assert.equal(safeNext("/login?x=1"), "/cabinet");
});

test("loginHref encodes next for safe internal return", () => {
  assert.equal(loginHref(), "/login");
  assert.equal(loginHref("/cabinet"), "/login");
  assert.equal(loginHref("/search"), "/login?next=%2Fsearch");
});
