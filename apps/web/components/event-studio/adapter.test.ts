import test from "node:test";
import assert from "node:assert/strict";
import {
  budgetHintFromSelection,
  isDraftVersionConflict,
  mapCatalogTalent,
  mapCatalogVenue,
} from "./adapter";
import type { EventStudioDraft, TalentItem, VenueItem } from "./types";

const baseDraft: EventStudioDraft = {
  title: "Test",
  kind: "Свадьба",
  city: "Москва",
  date: "2026-09-12",
  startsAt: "17:00",
  endsAt: "23:00",
  guests: 80,
  talentIds: ["a1"],
  requirements: [],
  version: 2,
};

test("mapCatalogTalent uses server tariffs and availability", () => {
  const item = mapCatalogTalent(
    {
      id: "a1",
      name: "DJ Test",
      city: "Москва",
      category: "dj",
      verified: true,
      open_slots: 2,
      next_open_at: "2026-09-12T17:00:00+03:00",
      tariffs: [{ honorarium_rub: 60000 }],
    },
    "2026-09-12",
  );
  assert.equal(item.honorariumFrom, 60000);
  assert.equal(item.availability, "available");
});

test("budgetHint aggregates only selected server hints", () => {
  const talents: TalentItem[] = [
    {
      id: "a1",
      name: "DJ",
      categoryCode: "dj",
      roleLabel: "DJ",
      honorariumFrom: 60000,
      verified: true,
      availability: "available",
      availabilityLabel: "ok",
      confirmedAt: null,
      initials: "DJ",
      tone: "graphite",
    },
  ];
  const venues: VenueItem[] = [{ id: "v1", name: "Hall", city: "Москва", honorariumFrom: 100000 }];
  const hint = budgetHintFromSelection(talents, venues, { ...baseDraft, talentIds: ["a1"], venueId: "v1" });
  assert.ok(hint);
  assert.equal(hint?.minRub, 160000);
  assert.equal(hint?.isEstimate, true);
});

test("isDraftVersionConflict detects stale payload", () => {
  assert.equal(isDraftVersionConflict({ ...baseDraft, version: 3 }, { ...baseDraft, version: 2 }), true);
  assert.equal(isDraftVersionConflict({ ...baseDraft, version: 2 }, { ...baseDraft, version: 2 }), false);
});

test("mapCatalogVenue preserves venue id", () => {
  const venue = mapCatalogVenue({
    id: "v1",
    name: "Дом у воды",
    city: "Москва",
    category: "venue",
    tariffs: [{ honorarium_rub: 250000 }],
  });
  assert.equal(venue.id, "v1");
  assert.equal(venue.honorariumFrom, 250000);
});
