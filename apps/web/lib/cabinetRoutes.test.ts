import assert from "node:assert/strict";
import test from "node:test";
import {
  cabinetPathForKind,
  cabinetPathForMode,
  isSupplyCabinet,
  orgKindToCabinetMode,
} from "./cabinetRoutes.ts";

test("orgKindToCabinetMode maps API kinds to UI routes", () => {
  assert.equal(orgKindToCabinetMode("customer"), "customer");
  assert.equal(orgKindToCabinetMode("artist"), "performer");
  assert.equal(orgKindToCabinetMode("venue"), "venue");
  assert.equal(orgKindToCabinetMode("unknown"), null);
});

test("cabinetPathForKind", () => {
  assert.equal(cabinetPathForKind("artist"), "/cabinet/performer");
  assert.equal(cabinetPathForKind("customer"), "/cabinet/customer");
});

test("isSupplyCabinet", () => {
  assert.equal(isSupplyCabinet("performer"), true);
  assert.equal(isSupplyCabinet("venue"), true);
  assert.equal(isSupplyCabinet("customer"), false);
});

test("cabinetPathForMode", () => {
  assert.equal(cabinetPathForMode("venue"), "/cabinet/venue");
});
