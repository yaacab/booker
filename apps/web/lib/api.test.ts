import test from "node:test";
import assert from "node:assert/strict";
import { clientEventFetchInit } from "./api";

test("clientEventFetchInit uses keepalive for navigation-safe analytics", () => {
  const init = clientEventFetchInit('{"name":"search.performed"}', {
    "Content-Type": "application/json",
  });
  assert.equal(init.method, "POST");
  assert.equal(init.keepalive, true);
});
