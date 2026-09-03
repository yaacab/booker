import assert from "node:assert/strict";
import test from "node:test";
import {
  cabinetHeadline,
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

test("cabinetHeadline", () => {
  assert.equal(cabinetHeadline("customer"), "Мои события");
  assert.equal(cabinetHeadline("performer"), "Ваши даты и заявки");
  assert.equal(cabinetHeadline("venue"), "Залы, даты и заявки");
});
