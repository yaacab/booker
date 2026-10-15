import assert from "node:assert/strict";
import test from "node:test";
import { flipKeyframes, saveHandoff, takeHandoff, HANDOFF_MAX_AGE_MS } from "./motion";

function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => { values.set(k, v); }, removeItem: (k: string) => { values.delete(k); } };
}
const rect = { left: 10, top: 20, width: 300, height: 200 };

test("fresh handoff is returned once and then consumed", () => {
  const s = memory();
  saveHandoff("role", rect, { role: "artist" }, s, 1000);
  const h = takeHandoff("role", () => true, s, 1500);
  assert.deepEqual(h?.rect, { x: 10, y: 20, w: 300, h: 200 });
  assert.equal(h?.data.role, "artist");
  assert.equal(takeHandoff("role", () => true, s, 1600), null);
});

test("stale handoff (Back/Forward later) falls back to plain entry", () => {
  const s = memory();
  saveHandoff("role", rect, { role: "venue" }, s, 1000);
  assert.equal(takeHandoff("role", () => true, s, 1000 + HANDOFF_MAX_AGE_MS + 1), null);
});

test("handoff for another profile is ignored and cleared", () => {
  const s = memory();
  saveHandoff("profile", rect, { id: "a" }, s, 1000);
  assert.equal(takeHandoff("profile", (d) => d.id === "b", s, 1100), null);
  assert.equal(s.values.size, 0);
});

test("malformed or zero-sized data never throws", () => {
  const s = memory();
  s.setItem("booker.handoff.role", "{not json");
  assert.equal(takeHandoff("role", () => true, s, 1), null);
  saveHandoff("role", { left: 0, top: 0, width: 0, height: 10 }, {}, s, 1);
  assert.equal(takeHandoff("role", () => true, s, 2), null);
});

test("denied storage is tolerated", () => {
  const denied = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); }, removeItem: () => { throw new Error("denied"); } };
  assert.doesNotThrow(() => saveHandoff("role", rect, {}, denied, 1));
  assert.equal(takeHandoff("role", () => true, denied, 2), null);
});

test("FLIP keyframes map the final box onto the origin box", () => {
  const [first, last] = flipKeyframes({ x: 100, y: 50, w: 200, h: 100 }, { x: 0, y: 0, w: 400, h: 400 });
  assert.equal(first.transform, "translate(100px, 50px) scale(0.5, 0.25)");
  assert.equal(last.transform, "translate(0, 0) scale(1, 1)");
});
