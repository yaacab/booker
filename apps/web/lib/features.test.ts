import assert from "node:assert/strict";
import test from "node:test";
import { isEventStudioMapV1 } from "./features.ts";

test("E05: default OFF without query or env", () => {
  const prev = process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  delete process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  assert.equal(isEventStudioMapV1(new URLSearchParams("")), false);
  assert.equal(isEventStudioMapV1(null), false);
  if (prev === undefined) delete process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  else process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = prev;
});

test("E05: query 1 enables, query 0 disables even if env on", () => {
  const prev = process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = "1";
  assert.equal(isEventStudioMapV1(new URLSearchParams("event_studio_map_v1=1")), true);
  assert.equal(isEventStudioMapV1(new URLSearchParams("event_studio_map_v1=0")), false);
  if (prev === undefined) delete process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  else process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = prev;
});

test("E05: env 1 enables when query absent", () => {
  const prev = process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = "1";
  assert.equal(isEventStudioMapV1(new URLSearchParams("")), true);
  process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = "0";
  assert.equal(isEventStudioMapV1(new URLSearchParams("")), false);
  if (prev === undefined) delete process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  else process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 = prev;
});
