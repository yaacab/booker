import test from "node:test";
import assert from "node:assert/strict";
import {
  budgetHintFromSelection,
  getOrCreateSubmitIdempotencyKey,
  isDraftVersionConflict,
  mapCatalogTalent,
  mapCatalogVenue,
  peekSubmitIdempotencyResult,
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

test("mapCatalogVenue marks synthetic availability", () => {
  const venue = mapCatalogVenue({
    id: "v2",
    name: "Artplay",
    city: "Москва",
    category: "venue",
    availability_mode: "synthetic",
    tariffs: [{ honorarium_rub: 150000 }],
  });
  assert.equal(venue.availabilityLabel, "Календарь ориентировочный");
});

test("getOrCreateSubmitIdempotencyKey is stable and peek finds cached result", () => {
  const store = new Map<string, string>();
  const g = globalThis as {
    window?: unknown;
    sessionStorage?: Storage;
  };
  const prevWindow = g.window;
  const prevSession = g.sessionStorage;
  g.window = globalThis;
  g.sessionStorage = {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => {
      store.set(k, String(v));
    },
    removeItem: (k) => {
      store.delete(k);
    },
    clear: () => store.clear(),
    key: () => null,
    get length() {
      return store.size;
    },
  } as Storage;

  try {
    const a = getOrCreateSubmitIdempotencyKey();
    const b = getOrCreateSubmitIdempotencyKey();
    assert.equal(a, b);
    assert.equal(peekSubmitIdempotencyResult(a), null);
    store.set("booker.eventStudioSubmitKey:result", "evt-1");
    assert.equal(peekSubmitIdempotencyResult(a), "evt-1");
    assert.equal(peekSubmitIdempotencyResult("other-key"), null);
  } finally {
    if (prevWindow === undefined) delete g.window;
    else g.window = prevWindow;
    if (prevSession === undefined) delete g.sessionStorage;
    else g.sessionStorage = prevSession;
  }
});
