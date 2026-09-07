"use client";

import Link from "next/link";
import { useState } from "react";
import { formatWhen, money } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerRequest } from "../types";

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

type RequestsInboxWidgetProps = {
  requests: PerformerRequest[];
  role: string;
  offerBusy: string | null;
  onSendOffer: (item: PerformerRequest) => void;
};

export function RequestsInboxWidget({ requests, role, offerBusy, onSendOffer }: RequestsInboxWidgetProps) {
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const sorted = [...requests].sort((a, b) => (b.event_date || "").localeCompare(a.event_date || ""));
  const visible = sorted.filter(r => filter === "all" || (filter === "new" ? !r.offer_id && !r.booking_id : Boolean(r.offer_id || r.booking_id)));
  const selected = visible.find(r => r.id === selectedId) || visible[0];

  return (
    <DashboardWidget
      title="Все входящие"
      hint="Полный список заявок организации"
      accent="performer"
      span="full"
      isEmpty={sorted.length === 0}
      empty="Заявки появятся, когда заказчик отправит запрос на ваш свободный слот."
    >
      <div className="request-filters" role="group" aria-label="Фильтр заявок">
        {[["all","Все"],["new","Без предложения"],["progress","С предложением"]].map(([value,label]) => <button type="button" key={value} className="secondary" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}
      </div>
      <div className="request-workspace">
      <ul className="request-list" aria-label="Выбор заявки">
        {visible.map(r => <li key={r.id}><button type="button" className="secondary" aria-pressed={r.id === selected?.id} onClick={() => setSelectedId(r.id)}><strong>{r.event_title}</strong><span>{formatWhen(r.event_date)}</span><span>{money(r.honorarium_rub)}</span></button></li>)}
      </ul>
      <ul className="dashboard-list request-detail" data-testid="performer-requests-inbox" aria-live="polite">
        {(selected ? [selected] : []).map((r) => {
          const pendingOffer = !r.offer_id && !r.booking_id;
          return (
            <li key={r.id}>
              <article className="dashboard-action-card">
                <strong>{r.event_title}</strong>
                <span className={`chip ${chipCls(r.status)}`}>{STATUS_LABEL[r.status] || r.status}</span>
                {r.event_date ? <span className="mono">{formatWhen(r.event_date)}</span> : null}
                <span className="timeline">Стоимость в витрине: {money(r.honorarium_rub)}</span>
                {r.booking_id ? (
                  <Link className="btn" href={`/deals/${r.booking_id}`}>
                    Deal Room
                  </Link>
                ) : r.offer_id ? (
                  <span className="timeline">Предложение отправлено</span>
                ) : pendingOffer && role !== "viewer" ? (
                  <button type="button" disabled={offerBusy === r.id} onClick={() => onSendOffer(r)}>
                    {offerBusy === r.id ? "Отправляем…" : "Ответить предложением"}
                  </button>
                ) : pendingOffer ? (
                  <p className="timeline">Только просмотр</p>
                ) : null}
              </article>
            </li>
          );
        })}
      </ul>
      {!selected ? <p className="timeline">В этой категории пока нет заявок.</p> : null}
      </div>
    </DashboardWidget>
  );
}
