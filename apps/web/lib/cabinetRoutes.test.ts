import assert from "node:assert/strict";
import test from "node:test";
import {
  cabinetHeadline,
  cabinetPathForKind,
  cabinetPathForMode,
  cabinetSectionPath,
  isSupplyCabinet,
  orgKindToCabinetMode,
  supplyCalendarHref,
  supplyRequestsHref,
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
  assert.equal(cabinetHeadline("customer"), "Студия событий");
  assert.equal(cabinetHeadline("performer"), "Календарь исполнителя");
  assert.equal(cabinetHeadline("venue"), "Пульт площадки");
});

test("E16: supply calendar and requests have distinct URLs", () => {
  assert.equal(supplyCalendarHref("performer"), "/cabinet/performer/calendar");
  assert.equal(supplyRequestsHref("performer"), "/cabinet/performer/requests");
  assert.notEqual(supplyCalendarHref("performer"), supplyRequestsHref("performer"));
  assert.equal(supplyCalendarHref("venue"), "/cabinet/venue/calendar");
  assert.equal(supplyRequestsHref("venue"), "/cabinet/venue/requests");
  assert.equal(cabinetSectionPath("performer", "home"), "/cabinet/performer");
  assert.equal(cabinetPathForMode("venue"), "/cabinet/venue");
});
