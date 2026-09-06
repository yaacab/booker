import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDealRoomAccents,
  dealRoomAccentDefs,
  orgKindToDealRoomAccentKind,
} from "./dealRoomAccents";

const sampleRoom = {
  booking_id: "bk-1",
  status: "Negotiation",
  event_id: "ev-1",
  event_title: "Свадьба",
  requirement_id: "req-1",
  next_step: "Подтвердить условия",
  quote: {
    quote_id: "q-1",
    honorarium_rub: 100_000,
    total_rub: 100_000,
    customer_ack: false,
    supplier_ack: true,
  },
  payment: null,
  contract: null,
  hold: null,
  documents: [{ kind: "attachment", label: "Райдер DJ", signed: false }],
};

test("orgKindToDealRoomAccentKind maps workspace kinds", () => {
  assert.equal(orgKindToDealRoomAccentKind("customer"), "customer");
  assert.equal(orgKindToDealRoomAccentKind("artist"), "performer");
  assert.equal(orgKindToDealRoomAccentKind("venue"), "venue");
});

test("dealRoomAccentDefs returns role-specific accent titles", () => {
  assert.deepEqual(
    dealRoomAccentDefs("customer").map((a) => a.title),
    ["Состав", "Итог", "Подтверждения", "Оплата", "Следующие шаги"],
  );
  assert.deepEqual(
    dealRoomAccentDefs("performer").map((a) => a.title),
    ["Обязательства", "Райдер", "Логистика", "Задачи", "Выплата"],
  );
  assert.deepEqual(
    dealRoomAccentDefs("venue").map((a) => a.title),
    ["Зал", "Ресурсы", "Монтаж", "Допуск", "Правила"],
  );
});

test("buildDealRoomAccents keeps shared quote_id in customer total", () => {
  const customerTotal = buildDealRoomAccents("customer", sampleRoom).find((a) => a.id === "total");
  assert.equal(customerTotal?.detail, "quote_id: q-1");
  const performerPayout = buildDealRoomAccents("performer", sampleRoom).find((a) => a.id === "payout");
  assert.match(performerPayout?.body ?? "", /100/);
  const venueHall = buildDealRoomAccents("venue", sampleRoom).find((a) => a.id === "hall");
  assert.equal(venueHall?.detail, "deal_id: bk-1");
});

test("buildDealRoomAccents surfaces rider for performer", () => {
  const rider = buildDealRoomAccents("performer", sampleRoom).find((a) => a.id === "rider");
  assert.match(rider?.body ?? "", /Райдер DJ/);
});
