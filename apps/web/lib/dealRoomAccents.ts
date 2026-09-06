import type { OrgKind } from "./cabinetRoutes";

export type DealRoomAccentKind = "customer" | "performer" | "venue";

export type DealRoomAccentId =
  | "composition"
  | "total"
  | "confirmations"
  | "payment"
  | "next_steps"
  | "obligations"
  | "rider"
  | "logistics"
  | "tasks"
  | "payout"
  | "hall"
  | "resources"
  | "setup"
  | "access"
  | "rules";

export type DealRoomAccentDef = {
  id: DealRoomAccentId;
  title: string;
  hint: string;
};

export type DealRoomAccentView = DealRoomAccentDef & {
  body: string;
  detail?: string;
};

export type DealRoomAccentSource = {
  booking_id: string;
  status: string;
  event_id?: string;
  event_title?: string;
  requirement_id?: string | null;
  next_step: string;
  quote: {
    quote_id: string;
    honorarium_rub: number;
    total_rub: number;
    customer_ack: boolean;
    supplier_ack: boolean;
  };
  payment: { status: string; amount_rub: number } | null;
  contract: { customer_signed: boolean; supplier_signed: boolean } | null;
  hold?: { status: string; expires_at: string } | null;
  documents?: { kind: string; label: string; signed: boolean }[];
};

const CUSTOMER: DealRoomAccentDef[] = [
  { id: "composition", title: "Состав", hint: "Позиция события и участники" },
  { id: "total", title: "Итог", hint: "Сумма с сервера по quote_id" },
  { id: "confirmations", title: "Подтверждения", hint: "Ack обеих сторон" },
  { id: "payment", title: "Оплата", hint: "Статус счёта и платежа" },
  { id: "next_steps", title: "Следующие шаги", hint: "Что сделать дальше" },
];

const PERFORMER: DealRoomAccentDef[] = [
  { id: "obligations", title: "Обязательства", hint: "Договор и условия услуги" },
  { id: "rider", title: "Райдер", hint: "Технические требования" },
  { id: "logistics", title: "Логистика", hint: "Дата, hold и Event Room" },
  { id: "tasks", title: "Задачи", hint: "Действия по статусу сделки" },
  { id: "payout", title: "Выплата", hint: "Гонорар и расчёт" },
];

const VENUE: DealRoomAccentDef[] = [
  { id: "hall", title: "Зал", hint: "Площадка и слот" },
  { id: "resources", title: "Ресурсы", hint: "Документы и материалы" },
  { id: "setup", title: "Монтаж", hint: "Подготовка и тайминг" },
  { id: "access", title: "Допуск", hint: "Подписи и допуск на площадку" },
  { id: "rules", title: "Правила", hint: "Условия площадки и ack" },
];

export function orgKindToDealRoomAccentKind(kind: OrgKind | string | null | undefined): DealRoomAccentKind {
  if (kind === "artist") return "performer";
  if (kind === "venue") return "venue";
  return "customer";
}

export function dealRoomAccentDefs(kind: DealRoomAccentKind): DealRoomAccentDef[] {
  if (kind === "performer") return PERFORMER;
  if (kind === "venue") return VENUE;
  return CUSTOMER;
}

function ackSummary(q: DealRoomAccentSource["quote"]): string {
  if (q.customer_ack && q.supplier_ack) return "подтверждено обеими сторонами";
  if (q.customer_ack) return "подтвердил только заказчик";
  if (q.supplier_ack) return "подтвердил только исполнитель";
  return "ожидает подтверждений";
}

function contractSummary(c: DealRoomAccentSource["contract"]): string {
  if (!c) return "договор ещё не создан";
  if (c.customer_signed && c.supplier_signed) return "договор подписан обеими сторонами";
  if (c.customer_signed || c.supplier_signed) return "ожидается вторая подпись";
  return "черновик договора готов к подписанию";
}

function paymentSummary(p: DealRoomAccentSource["payment"]): string {
  if (!p) return "счёт не выставлен";
  return `${p.status} · ${p.amount_rub.toLocaleString("ru-RU")} ₽`;
}

function riderSummary(docs: DealRoomAccentSource["documents"]): string {
  const riders = (docs ?? []).filter((d) => /райдер|rider/i.test(d.label));
  if (riders.length === 0) return "райдер уточняется в чате и вкладке «Документы»";
  return riders.map((d) => `${d.label}${d.signed ? " · подписано" : ""}`).join("; ");
}

function taskLines(status: string): string {
  const map: Record<string, string> = {
    Negotiation: "Подтвердить условия · проверить quote_id",
    DateHeld: "Подписать договор · подготовить райдер",
    AwaitingContract: "Подписать договор OTP",
    AwaitingPayment: "Дождаться оплаты заказчика",
    Confirmed: "Подготовиться к событию · проверить логистику",
  };
  return map[status] ?? "Следовать статусу сделки в журнале";
}

function buildAccentBody(id: DealRoomAccentId, room: DealRoomAccentSource): { body: string; detail?: string } {
  switch (id) {
    case "composition":
      return {
        body: room.event_title || "Событие не привязано",
        detail: room.requirement_id ? `requirement_id: ${room.requirement_id}` : undefined,
      };
    case "total":
      return {
        body: `${room.quote.total_rub.toLocaleString("ru-RU")} ₽`,
        detail: `quote_id: ${room.quote.quote_id}`,
      };
    case "confirmations":
      return { body: ackSummary(room.quote) };
    case "payment":
      return { body: paymentSummary(room.payment) };
    case "next_steps":
      return { body: room.next_step };
    case "obligations":
      return { body: contractSummary(room.contract), detail: ackSummary(room.quote) };
    case "rider":
      return { body: riderSummary(room.documents) };
    case "logistics":
      return {
        body: room.hold?.status === "active" ? "Дата удерживается" : "Hold не активен",
        detail: room.event_id ? "Event Control Room · слот и состав" : undefined,
      };
    case "tasks":
      return { body: taskLines(room.status) };
    case "payout":
      return {
        body: `гонорар ${room.quote.honorarium_rub.toLocaleString("ru-RU")} ₽`,
        detail: paymentSummary(room.payment),
      };
    case "hall":
      return {
        body: room.event_title || "Зал и слот",
        detail: room.booking_id ? `deal_id: ${room.booking_id}` : undefined,
      };
    case "resources":
      return {
        body:
          (room.documents?.length ?? 0) > 0
            ? `${room.documents!.length} документ(ов) в сделке`
            : "материалы добавляются во вкладке «Документы»",
      };
    case "setup":
      return {
        body: room.hold?.status === "active" ? "Монтаж после hold даты" : "Монтаж согласуется после ack",
        detail: room.next_step,
      };
    case "access":
      return { body: contractSummary(room.contract) };
    case "rules":
      return { body: ackSummary(room.quote), detail: "Правила площадки фиксируются в условиях и чате" };
    default:
      return { body: "—" };
  }
}

export function buildDealRoomAccents(
  kind: DealRoomAccentKind,
  room: DealRoomAccentSource,
): DealRoomAccentView[] {
  return dealRoomAccentDefs(kind).map((def) => {
    const content = buildAccentBody(def.id, room);
    return { ...def, ...content };
  });
}
