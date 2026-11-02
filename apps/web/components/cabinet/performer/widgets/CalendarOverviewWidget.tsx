"use client";

import Link from "next/link";
import { useState } from "react";
import { api, isWriteRole } from "@/lib/api";
import { formatClock, formatWhen, parseBookerDate } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import { MonthCalendar } from "../../MonthCalendar";
import type { PerformerBooking } from "../types";
import { usePerformerCalendarOverview } from "../usePerformerCalendarOverview";

export function CalendarOverviewWidget({
  orgId,
  artistId,
  bookings,
  compact = false,
  role = "",
}: {
  orgId: string;
  artistId: string;
  bookings: PerformerBooking[];
  compact?: boolean;
  role?: string;
}) {
  const { slots, openSlots, activeVacation, confirmedDates, loading, error, reload } =
    usePerformerCalendarOverview(orgId, artistId, bookings);
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");
  const canManage = isWriteRole(role);

  async function deleteOpenSlot(slotId: string) {
    if (!canManage) return;
    if (!window.confirm("Удалить этот открытый слот?")) return;
    setBusyId(slotId);
    setActionError("");
    try {
      await api(`/slots/${encodeURIComponent(slotId)}`, { method: "DELETE" });
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось удалить слот");
    } finally {
      setBusyId("");
    }
  }

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
    {openSlots.length ? (
      <ul className="dashboard-list" data-testid="performer-open-slot-actions">
        {openSlots.slice(0, 12).map((slot) => (
          <li key={slot.id}>
            <span>
              {formatWhen(slot.starts_at)} — {formatClock(slot.ends_at)}
            </span>
            {canManage ? (
              <button
                type="button"
                className="linkish"
                disabled={busyId === slot.id}
                onClick={() => void deleteOpenSlot(slot.id)}
              >
                {busyId === slot.id ? "…" : "Удалить"}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    ) : null}
    {actionError ? <p style={{ color: "var(--danger)" }}>{actionError}</p> : null}
  </div>;
}
