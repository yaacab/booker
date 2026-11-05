import test from "node:test";
import assert from "node:assert/strict";
import { mapCatalogTalent, mapCatalogVenue } from "./adapter";
import type { EventStudioDraft } from "./types";

const baseDraft: EventStudioDraft = {
  title: "Test", kind: "Свадьба", city: "Москва", date: "2027-02-11", startsAt: "19:00", endsAt: "23:30",
  guests: 80, talentIds: ["a1", "a2"], requirements: [], version: 2,
};

test("M04 venue cards keep the catalogue halls with capacity (no invented halls)", () => {
  const v = mapCatalogVenue({ id: "v1", name: "Лофт", city: "Москва", category: "venue", matching_halls: [{ id: "h1", name: "Большой", capacity: 120 }, { id: "h2", name: "Камерный" }] });
  assert.deepEqual(v.halls, [{ id: "h1", name: "Большой", capacity: 120 }, { id: "h2", name: "Камерный", capacity: null }]);
  const none = mapCatalogVenue({ id: "v2", name: "Зал", city: "Москва", category: "venue" });
  assert.equal(none.halls, undefined);
});

test("M04 sends every chosen artist, the venue and the chosen hall as a note; one event per key", async () => {
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, String(v)); }, removeItem: (k: string) => { store.delete(k); } } as Storage;
  const prev = { window: globalThis.window, session: globalThis.sessionStorage, local: globalThis.localStorage, fetch: globalThis.fetch };
  Object.assign(globalThis, { window: globalThis, sessionStorage: storage, localStorage: storage });
  const calls: { url: string; body: any }[] = [];
  globalThis.fetch = async (url, init) => {
    const path = String(url); const body = init?.body ? JSON.parse(String(init.body)) : null; calls.push({ url: path, body });
    return new Response(JSON.stringify(path.endsWith("/me") ? { organizations: [{ id: "c1", kind: "customer" }] } : path.endsWith("/events") ? { id: "e1", requirements: [] } : { id: "r1" }), { status: 200 });
  };
  try {
    const { submitEventStudioDraft } = await import("./adapter");
    const { fromVisual, toVisual } = await import("./v5Adapter");
    const base = { ...baseDraft, venueId: "v1" };
    const d = fromVisual(base, { ...toVisual(base), artists: ["a1", "a2"], hall: "Большой", budget: 250000 } as any);
    const talents = [mapCatalogTalent({ id: "a1", name: "A", city: "Москва", category: "dj" }), mapCatalogTalent({ id: "a2", name: "B", city: "Москва", category: "host" })];
    const r = await submitEventStudioDraft(d, talents, "m04-key");
    assert.equal(r.eventId, "e1");
    const create = calls.find((c) => c.url.endsWith("/events"))!.body;
    assert.match(create.notes, /зал:Большой/);
    assert.equal(create.budget_rub, 250000);
    assert.deepEqual(calls.filter((c) => c.url.endsWith("/requests")).map((c) => [c.body.resource_type, c.body.resource_id]), [["artist", "a1"], ["artist", "a2"], ["venue", "v1"]]);
    await submitEventStudioDraft(d, talents, "m04-key");
    assert.equal(calls.filter((c) => c.url.endsWith("/events")).length, 1);
  } finally {
    globalThis.fetch = prev.fetch;
    for (const [key, value] of [["window", prev.window], ["sessionStorage", prev.session], ["localStorage", prev.local]] as const) { if (value === undefined) delete (globalThis as any)[key]; else (globalThis as any)[key] = value; }
  }
});

test("published artist without a filled calendar is labelled honestly, not as free", () => {
  const t = mapCatalogTalent({ id: "a9", name: "Без календаря", city: "Москва", category: "dj", verified: true, open_slots: 0, next_open_at: null, calendar_status: "unfilled" } as any);
  assert.match(t.availabilityLabel, /Календарь не заполнен/);
});
