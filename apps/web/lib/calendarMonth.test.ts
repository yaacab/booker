import test from "node:test";
import assert from "node:assert/strict";
import { calendarDayStatus, entriesOnDay, monthCells, moscowDay } from "./calendarMonth";

test("calendar uses Moscow day across UTC midnight", () => {
  assert.equal(moscowDay("2026-09-06T22:00:00Z"), "2026-09-07");
  assert.equal(moscowDay("2026-09-07T00:00:00"), "2026-09-07");
});

test("day summary keeps active availability when a cancelled interval exists", () => {
  const entry = { id: "slot", starts_at: "2026-09-07T18:00:00", ends_at: "2026-09-07T22:00:00" };
  assert.equal(calendarDayStatus([{ ...entry, status: "cancelled" }, { ...entry, id: "open", status: "open" }]), "open");
  assert.equal(calendarDayStatus([{ ...entry, status: "open" }, { ...entry, id: "hold", status: "held" }]), "held");
  assert.equal(calendarDayStatus([{ ...entry, status: "held" }, { ...entry, id: "booked", status: "booked" }]), "booked");
  assert.equal(calendarDayStatus([]), "unknown");
});
test("month grid starts Monday and includes leap day and year rollover", () => {
  const leap = monthCells(2024, 1);
  assert.equal(leap.length, 42);
  assert.equal(leap[0], "2024-01-29");
  assert.ok(leap.includes("2024-02-29"));
  assert.equal(monthCells(2026, 0)[0], "2025-12-29");
});
test("overnight slots occupy both days but midnight end excludes next day", () => {
  const entries = [{ id:"one", status:"booked", starts_at:"2026-09-07T22:00:00+03:00", ends_at:"2026-09-08T02:00:00+03:00" }];
  assert.equal(entriesOnDay(entries,"2026-09-07").length, 1);
  assert.equal(entriesOnDay(entries,"2026-09-08").length, 1);
  assert.equal(entriesOnDay(entries,"2026-09-09").length, 0);
  assert.equal(entriesOnDay([{...entries[0],ends_at:"2026-09-08T00:00:00+03:00"}],"2026-09-08").length, 0);
});
