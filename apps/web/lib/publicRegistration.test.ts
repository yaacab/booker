import assert from "node:assert/strict";
import test from "node:test";
import { isPublicRegistrationEnabled } from "./publicRegistration.ts";

test("public registration requires the exact server opt-in", () => {
  assert.equal(isPublicRegistrationEnabled("1"), true);

  for (const value of [undefined, "", "0", "true", "yes", "1 "]) {
    assert.equal(isPublicRegistrationEnabled(value), false);
  }
});
