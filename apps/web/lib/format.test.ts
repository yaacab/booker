import test from "node:test";
import assert from "node:assert/strict";
import { formatWhen, money, parseBookerDate, moscowDate } from "./format";

test("parseBookerDate treats legacy naive API ISO as UTC", () => {
  const d = parseBookerDate("2026-09-16T18:00:00");
  assert.equal(d.toISOString(), "2026-09-16T18:00:00.000Z");
});

test("parseBookerDate keeps explicit UTC offset", () => {
  const d = parseBookerDate("2026-09-16T18:00:00Z");
  assert.equal(d.toISOString(), "2026-09-16T18:00:00.000Z");
});

test("formatWhen for naive catalog next_open_at is stable under TZ=UTC", () => {
  const prev = process.env.TZ;
  process.env.TZ = "UTC";
  try {
    assert.equal(formatWhen("2026-09-16T18:00:00"), "16 сентября в 21:00");
  } finally {
    if (prev === undefined) delete process.env.TZ;
    else process.env.TZ = prev;
  }
});

test("date-only selection stays on the Moscow day while instants cross midnight",()=>{
  assert.equal(moscowDate("2026-09-16"),"2026-09-16");
  assert.equal(parseBookerDate("2026-09-16").toISOString(),"2026-09-15T21:00:00.000Z");
  assert.equal(moscowDate("2026-09-16T22:00:00Z"),"2026-09-17");
  assert.equal(formatWhen("2026-09-16T18:00:00+03:00"),"16 сентября в 18:00");
});

test("money uses regular spaces (no NBSP) for SSR/client parity", () => {
  const s = money(180000);
  assert.equal(s, "180 000 ₽");
  assert.ok(!/[\u00a0\u202f]/.test(s));
});
