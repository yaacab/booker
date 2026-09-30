"use client";

import Link from "next/link";
import { formatClock, formatWhen, parseBookerDate } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import { MonthCalendar } from "../../MonthCalendar";
import type { PerformerBooking } from "../types";
import { usePerformerCalendarOverview } from "../usePerformerCalendarOverview";

export function CalendarOverviewWidget({ orgId, artistId, bookings, compact = false }: {
  orgId: string; artistId: string; bookings: PerformerBooking[]; compact?: boolean;
}) {
  const { slots, openSlots, activeVacation, confirmedDates, loading, error } = usePerformerCalendarOverview(orgId, artistId, bookings);

  if (compact) return <DashboardWidget title="Открытые слоты" accent="performer">
    <div className="workspace-widget-link"><Link href="/cabinet/performer/calendar">Управлять →</Link></div>
    {loading ? <p className="timeline" role="status">Загружаем даты…</p> : error ? <p className="timeline" role="alert">{error}</p> : openSlots.length ? <div className="workspace-open-dates">
      {openSlots.slice(0, 6).map(slot => {
        const date = parseBookerDate(slot.starts_at);
        return <Link href="/cabinet/performer/calendar" key={slot.id} title={`${formatWhen(slot.starts_at)} — ${formatClock(slot.ends_at)}`}>
          <strong>{date.toLocaleDateString("ru-RU", { day: "numeric", timeZone: "Europe/Moscow" })}</strong>
          <span>{date.toLocaleDateString("ru-RU", { month: "short", timeZone: "Europe/Moscow" })}</span>
          <small>{date.toLocaleDateString("ru-RU", { weekday: "short", timeZone: "Europe/Moscow" })}</small>
        </Link>;
      })}
      <Link className="workspace-add-date" href="/cabinet/performer/calendar" aria-label="Добавить свободные даты"><strong>＋</strong><small>Добавить</small></Link>
    </div> : <div className="workspace-soft-empty"><p>Пока нет открытых дат.</p><Link href="/cabinet/performer/calendar">Настроить доступность →</Link></div>}
    <p className="workspace-availability-note">Открытые даты помогают заказчикам найти вас.</p>
  </DashboardWidget>;

  return <div className="workspace-calendar-panel" data-testid="performer-calendar-overview">
    {loading ? <p className="timeline" role="status">Загружаем календарь…</p> : null}
    {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
    {!loading && !error ? <MonthCalendar entries={slots} manageHref="#calendar-manage" /> : null}
    <div className="workspace-calendar-summary">
      <span>Открытых слотов <strong>{openSlots.length}</strong></span>
      <span>Подтверждённых дат <strong>{confirmedDates}</strong></span>
      {activeVacation ? <span>Отпуск до {activeVacation.ends_at ? formatWhen(activeVacation.ends_at) : "—"}</span> : null}
      <a href="#supply-settings" onClick={() => { const details = document.getElementById("supply-settings"); if (details instanceof HTMLDetailsElement) details.open = true; }}>Импорт календаря и отпуск →</a>
    </div>
  </div>;
}
