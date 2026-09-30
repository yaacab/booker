import assert from "node:assert/strict";
import test from "node:test";
import { isInvestorDemoEnabled } from "./investorDemo.ts";

test("investor demo is enabled only by the exact server flag value", () => {
  assert.equal(isInvestorDemoEnabled("1"), true);

  for (const value of [undefined, "", "0", "true", "yes", "1 "]) {
    assert.equal(isInvestorDemoEnabled(value), false);
  }
});
