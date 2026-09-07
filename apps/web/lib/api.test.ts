import test from "node:test";
import assert from "node:assert/strict";
import { apiErrorMessage, clientEventFetchInit } from "./api";

test("clientEventFetchInit uses keepalive for navigation-safe analytics", () => {
  const init = clientEventFetchInit('{"name":"search.performed"}', {
    "Content-Type": "application/json",
  });
  assert.equal(init.method, "POST");
  assert.equal(init.keepalive, true);
});

test("API errors preserve actionable conflicts without exposing HTML or server exceptions", () => {
  assert.equal(apiErrorMessage(409, "Дата уже занята"), "Дата уже занята");
  assert.equal(apiErrorMessage(403, "Недостаточно прав"), "Недостаточно прав");
  assert.doesNotMatch(apiErrorMessage(404, "<!DOCTYPE html><h1>Proxy error</h1>"), /DOCTYPE|Proxy/);
  assert.doesNotMatch(apiErrorMessage(500, "Database exception: private@example.test"), /Database|private/);
  assert.doesNotMatch(apiErrorMessage(422, [{ msg: "Invalid", input: "private@example.test" }]), /private/);
  assert.ok(apiErrorMessage(200, undefined));
});
