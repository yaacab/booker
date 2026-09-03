import test from "node:test";
import assert from "node:assert/strict";
import { slotsFromDraft } from "./PuzzleBoard";

test("slotsFromDraft maps date, venue, and up to four talent roles into six slots", () => {
  const slots = slotsFromDraft({
    date: "2026-09-12",
    dateLabel: "12 сен",
    venueName: "Loft River",
    hasVenue: true,
    talents: [
      { id: "t1", roleLabel: "Ведущий", name: "Анна" },
      { id: "t2", roleLabel: "DJ", name: "Илья" },
    ],
  });

  assert.equal(slots.length, 6);
  assert.equal(slots[0].id, "date");
  assert.equal(slots[0].filled, true);
  assert.equal(slots[0].detail, "12 сен");
  assert.equal(slots[1].id, "venue");
  assert.equal(slots[1].filled, true);
  assert.equal(slots[1].detail, "Loft River");
  assert.equal(slots[2].id, "talent-t1");
  assert.equal(slots[2].filled, true);
  assert.equal(slots[2].label, "Ведущий");
  assert.equal(slots[3].id, "talent-t2");
  assert.equal(slots[3].filled, true);
  assert.equal(slots[3].label, "DJ");
  assert.equal(slots[4].filled, false);
  assert.equal(slots[5].filled, false);
});

test("slotsFromDraft keeps date and venue empty when draft fields are unset", () => {
  const slots = slotsFromDraft({
    date: "",
    dateLabel: "дата позже",
    hasVenue: false,
    talents: [],
  });

  assert.equal(slots[0].filled, false);
  assert.equal(slots[1].filled, false);
  assert.ok(slots.slice(2).every((s) => !s.filled));
});
