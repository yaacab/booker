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
      <p className="kicker">Сводка сделки</p>
      <p className="mono" data-testid="deal-room-ids">
        {room.booking_id} · quote_id: {room.quote.quote_id}
      </p>
      <p>
        Статус брони: <strong>{STATUS_LABEL[room.status] || room.status}</strong>
      </p>
      {room.event_id ? (
        <p>
          <Link href={`/events/${room.event_id}`}>{room.event_title || "Событие"}</Link>
        </p>
      ) : (
        <p className="timeline">Событие не привязано</p>
      )}
      <p>
        <span className="kicker">Следующее действие</span>
        <br />
        {room.next_step}
        <br />
        <span className="timeline">{nextActionHint(actionKind)}</span>
      </p>
      <DealRoomAccentGrid accents={accents} />
    </section>
  );
}
