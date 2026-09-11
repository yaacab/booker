"use client";

import Link from "next/link";
import { buildDealRoomAccents, type DealRoomAccentKind } from "@/lib/dealRoomAccents";
import { nextActionHint, STATUS_LABEL } from "@/lib/status";
import { DealRoomAccentGrid } from "./DealRoomAccentGrid";

type DealRoomSummaryProps = {
  accentKind: DealRoomAccentKind;
  room: {
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
  actionKind: string;
};

export function DealRoomSummary({ accentKind, room, actionKind }: DealRoomSummaryProps) {
  const accents = buildDealRoomAccents(accentKind, room);

  return (
    <section className="card deal-summary surface-glass">
      <div className="deal-content-heading"><h2>Сводка сделки</h2><span className="chip wait">{STATUS_LABEL[room.status] || room.status}</span></div>
      <div className="deal-next-step"><span className="deal-next-mark" aria-hidden="true">↗</span><div><p className="kicker">Следующее действие</p><strong>{room.next_step}</strong><p className="timeline">{actionKind === "ack" ? "Подтвердите актуальное предложение. Для продолжения нужно согласие обеих сторон." : actionKind === "contract" ? "Подпишите договор кодом из уведомлений." : nextActionHint(actionKind)}</p></div></div>
      <div className="deal-confirmations" aria-label="Подтверждение предложения"><div><span aria-hidden="true">{room.quote.customer_ack ? "✓" : "◷"}</span><span><strong>Заказчик</strong><small>{room.quote.customer_ack ? "Условия подтверждены" : "Ожидаем подтверждение"}</small></span></div><div><span aria-hidden="true">{room.quote.supplier_ack ? "✓" : "◷"}</span><span><strong>Исполнитель</strong><small>{room.quote.supplier_ack ? "Условия подтверждены" : "Ожидаем подтверждение"}</small></span></div></div>
      <DealRoomAccentGrid accents={accents} />
      <div className="deal-summary-footer">{room.event_id ? <Link href={`/events/${room.event_id}`}>{room.event_title || "Событие"} ↗</Link> : <span>Событие не привязано</span>}<details><summary>Реквизиты сделки</summary><p className="mono" data-testid="deal-room-ids">{room.booking_id} · quote_id: {room.quote.quote_id}</p></details></div>
    </section>
  );
}
