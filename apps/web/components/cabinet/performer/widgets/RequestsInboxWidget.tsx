"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { formatWhen, money, parseBookerDate } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { CabinetIcon } from "../../CabinetIcon";
import type { PerformerRequest } from "../types";

type Filter = "all" | "new" | "progress" | "archive";
const ARCHIVE = new Set(["Cancelled", "Declined", "Expired", "Completed"]);
function requestGroup(request: PerformerRequest): Filter {
  if (ARCHIVE.has(request.status)) return "archive";
  return request.offer_id || request.booking_id ? "progress" : "new";
}

export function RequestsInboxWidget({ requests, role, offerBusy, onSendOffer }: {
  requests: PerformerRequest[]; role: string; offerBusy: string | null; onSendOffer: (item: PerformerRequest, amount: number) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detailId = useId();
  const sorted = [...requests].sort((a, b) => (b.event_date || "").localeCompare(a.event_date || ""));
  const visible = sorted.filter(request => filter === "all" || requestGroup(request) === filter);
  const selected = visible.find(request => request.id === selectedId) || visible[0];
  const filters: [Filter, string][] = [["all", "Все"], ["new", "Новые"], ["progress", "В работе"], ["archive", "Архив"]];

  return <section className="workspace-inbox" aria-label="Входящие заявки">
    <div className="request-filters" role="group" aria-label="Фильтр заявок">
      {filters.map(([value, label]) => <button type="button" key={value} className="secondary" aria-pressed={filter === value} onClick={() => setFilter(value)}>
        {label} <span>{value === "all" ? requests.length : requests.filter(request => requestGroup(request) === value).length}</span>
      </button>)}
    </div>
    <div className="request-workspace">
      <ul className="request-list" aria-label="Выбор заявки">
        {visible.map(request => {
          const date = request.event_date ? parseBookerDate(request.event_date) : null;
          return <li key={request.id}><button type="button" className="secondary" aria-pressed={request.id === selected?.id} aria-controls={detailId} onClick={() => setSelectedId(request.id)}>
            <span className="request-date-tile" aria-hidden="true"><strong>{date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("ru-RU", { day: "numeric", timeZone: "Europe/Moscow" }) : "—"}</strong><small>{date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("ru-RU", { month: "short", timeZone: "Europe/Moscow" }) : "Дата"}</small></span>
            <span className="request-list-copy"><strong>{request.event_title}</strong><span>{[request.customer_name, formatWhen(request.event_date)].filter(Boolean).join(" · ")}</span><b>{request.honorarium_rub ? money(request.honorarium_rub) : "сумма не задана"}</b></span>
            {requestGroup(request) === "new" ? <i className="request-unread-dot" aria-label="Новая заявка" /> : null}
          </button></li>;
        })}
        {!visible.length ? <li className="workspace-soft-empty"><CabinetIcon name="request" /><strong>{requests.length ? "В этой категории пока нет заявок" : "Здесь будут новые заявки"}</strong><p>Когда заказчик отправит запрос на свободную дату, он появится здесь.</p></li> : null}
      </ul>
      <div className="request-detail" id={detailId} data-testid="performer-requests-inbox" aria-live="polite">
        {selected ? <article className="request-detail-content">
          <header><h2>{selected.event_title}</h2><span className={`chip ${requestGroup(selected) === "new" ? "live" : requestGroup(selected) === "archive" ? "bad" : "ok"}`}>{requestGroup(selected) === "new" ? "Новая" : STATUS_LABEL[selected.status] || selected.status}</span></header>
          <p className="request-detail-date"><CabinetIcon name="calendar" />{formatWhen(selected.event_date)}</p>
          <dl className="request-detail-facts">
            <div><dt>Заказчик</dt><dd>{selected.customer_name || "—"}</dd></div>
            <div><dt>Город</dt><dd>{selected.event_city || "—"}</dd></div>
            <div><dt>Гостей</dt><dd>{selected.guest_count ?? "—"}</dd></div>
            <div><dt>Бюджет заказчика</dt><dd>{selected.budget_rub ? `до ${money(selected.budget_rub)}` : "не указан"}</dd></div>
            {selected.brief?.hall ? <div><dt>Зал</dt><dd>{selected.brief.hall}</dd></div> : null}
            <div><dt>Райдер</dt><dd>{selected.brief?.rider?.length ? selected.brief.rider.join(", ") : "без особых требований"}</dd></div>
            {selected.brief?.wishes ? <div><dt>Пожелания</dt><dd>{selected.brief.wishes}</dd></div> : null}
            <div><dt>Ваш тариф в каталоге</dt><dd>{selected.honorarium_rub ? money(selected.honorarium_rub) : "не задан"}</dd></div>
            <div><dt>Статус заявки</dt><dd>{STATUS_LABEL[selected.status] || selected.status}</dd></div>
          </dl>
          <div className="request-detail-note"><CabinetIcon name="request" /><div><strong>{selected.booking_id ? "Обсуждение события" : selected.offer_id ? "Предложение отправлено" : "Ответьте на запрос"}</strong><p>{selected.booking_id ? "Все договорённости, документы и переписка — в комнате сделки." : selected.offer_id ? "Заказчик получит ваше предложение и сможет подтвердить условия." : "Отправьте предложение с выбранной датой и стоимостью. Итоговые условия можно согласовать в комнате сделки."}</p></div></div>
          <div className="request-detail-actions">
            {selected.booking_id ? <Link className="btn" href={`/deals/${selected.booking_id}`}>Открыть сделку <CabinetIcon name="arrow" /></Link>
              : !selected.offer_id && requestGroup(selected) !== "archive" && role !== "viewer" ? (() => {
                const raw = amounts[selected.id] ?? (selected.honorarium_rub ? String(selected.honorarium_rub) : "");
                const amount = Math.floor(Number(raw));
                const valid = raw !== "" && amount > 0;
                const overBudget = valid && !!selected.budget_rub && amount > selected.budget_rub;
                return <form className="request-offer-form" onSubmit={(e) => { e.preventDefault(); if (valid) onSendOffer(selected, amount); }}>
                  <label>Сумма вашего предложения, ₽<input inputMode="numeric" type="number" min={1} step={1} required value={raw} onChange={(e) => setAmounts((m) => ({ ...m, [selected.id]: e.target.value }))} aria-describedby={`${detailId}-offer-hint`} /></label>
                  <p id={`${detailId}-offer-hint`} className="timeline">{!valid && raw !== "" ? "Сумма должна быть больше нуля." : overBudget ? `Выше бюджета заказчика (до ${money(selected.budget_rub!)}) — объясните в сообщении, что входит в цену.` : "Комиссию платформы и итог для заказчика посчитает сервер: первая сделка заказчика — без комиссии."}</p>
                  <button type="submit" disabled={!valid || offerBusy === selected.id}>{offerBusy === selected.id ? "Отправляем…" : "Создать предложение"}<CabinetIcon name="arrow" /></button>
                </form>;
              })()
                : !selected.offer_id && role === "viewer" ? <p className="timeline">Предложения отправляет менеджер. Вам доступен просмотр заявки.</p> : null}
          </div>
        </article> : <div className="request-no-selection"><CabinetIcon name="request" /><h2>Заявки на ваши события</h2><p>Выберите заявку, чтобы посмотреть дату, стоимость и ответить заказчику.</p></div>}
      </div>
    </div>
  </section>;
}
