"use client";

import { useId, useMemo, useState } from "react";
import { CALENDAR_STATUS_LABELS, calendarDayStatus, entriesOnDay, monthCells, moscowDay, type CalendarEntry } from "@/lib/calendarMonth";
import { formatClock, formatWhen } from "@/lib/format";
import { CabinetIcon } from "./CabinetIcon";

const SHORT_LABELS: Record<string, string> = { booked: "Бронь", held: "Удержание", hold: "Удержание", blocked: "Закрыт" };

export function MonthCalendar({ entries, label = "Календарь доступности", manageHref }: { entries: CalendarEntry[]; label?: string; manageHref?: string }) {
  const today = moscowDay(new Date().toISOString());
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(() => new Date(`${today.slice(0, 7)}-01T12:00:00Z`));
  const [view, setView] = useState<"month" | "list">("month");
  const detailsId = useId();
  const cells = useMemo(() => monthCells(month.getUTCFullYear(), month.getUTCMonth()), [month]);
  const dayEntries = useMemo(() => new Map(cells.map(day => [day, entriesOnDay(entries, day)])), [cells, entries]);
  const visibleMonth = month.toISOString().slice(0, 7);
  const selectedEntries = dayEntries.get(selected) || entriesOnDay(entries, selected);
  const selectedStatus = calendarDayStatus(selectedEntries);
  const monthEntries = entries.filter(entry => cells.filter(day => day.startsWith(visibleMonth)).some(day => (dayEntries.get(day) || []).some(item => item.id === entry.id))).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  function moveMonth(offset: number) {
    const next = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + offset, 1, 12));
    setMonth(next);
    setSelected(next.toISOString().slice(0, 10));
  }
  function openManage() {
    if (!manageHref?.startsWith("#")) return;
    const target = document.getElementById(manageHref.slice(1));
    if (target instanceof HTMLDetailsElement) target.open = true;
  }
  return <section className="month-calendar" aria-label={label}>
    <div className="month-toolbar">
      <div className="month-navigation">
        <button type="button" className="secondary" onClick={() => { setSelected(today); setMonth(new Date(`${today.slice(0, 7)}-01T12:00:00Z`)); }}>Сегодня</button>
        <button type="button" className="secondary month-arrow" aria-label="Предыдущий месяц" onClick={() => moveMonth(-1)}>‹</button>
        <button type="button" className="secondary month-arrow" aria-label="Следующий месяц" onClick={() => moveMonth(1)}>›</button>
      </div>
      <h3 aria-live="polite">{month.toLocaleDateString("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" })}</h3>
      <div className="calendar-view-switch" role="group" aria-label="Вид календаря"><button type="button" aria-pressed={view === "month"} onClick={() => setView("month")}>Месяц</button><button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>Список</button></div>
    </div>
    {view === "month" ? <div className="month-layout">
      <div className="month-grid-panel">
        <div className="month-weekdays" aria-hidden="true">{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(day => <span key={day}>{day}</span>)}</div>
        <div className="month-days">
          {cells.map(day => {
            const items = dayEntries.get(day) || [];
            const status = calendarDayStatus(items);
            return <button type="button" key={day} className={`month-day status-${status}${day.startsWith(visibleMonth) ? "" : " adjacent"}`}
              aria-label={`${day}: ${CALENDAR_STATUS_LABELS[status] || "Доступность не опубликована"}${items.length ? `, интервалов: ${items.length}` : ""}`}
              aria-pressed={day === selected} aria-current={day === today ? "date" : undefined} aria-controls={detailsId}
              onClick={() => setSelected(day)}>
              <strong>{Number(day.slice(-2))}</strong>
              <span>{SHORT_LABELS[status] || CALENDAR_STATUS_LABELS[status] || ""}</span>
              {items.length > 1 ? <small className="month-slot-count">{items.length}</small> : null}
            </button>;
          })}
        </div>
        <div className="month-legend" aria-label="Обозначения календаря"><span><i className="status-open" />Свободен</span><span><i className="status-booked" />Бронь</span><span><i className="status-held" />Удержание</span><span><i className="status-busy" />Занят</span><span><i className="status-unknown" />Нет слотов</span></div>
      </div>
      <aside className="month-details" id={detailsId} aria-live="polite">
        <h3>{new Date(`${selected}T12:00:00+03:00`).toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Moscow" })}</h3>
        <span className={`calendar-status-pill status-${selectedStatus}`}>{CALENDAR_STATUS_LABELS[selectedStatus] || "Нет открытых слотов"}</span>
        {selectedEntries.length ? <ul>{selectedEntries.map(entry => <li key={entry.id}><strong>{entry.label || CALENDAR_STATUS_LABELS[entry.status] || entry.status}</strong><p><CabinetIcon name="clock" />{formatClock(entry.starts_at)} — {formatClock(entry.ends_at)}</p>{moscowDay(entry.starts_at) !== moscowDay(entry.ends_at) ? <small>До {formatWhen(entry.ends_at)}</small> : null}</li>)}</ul> : <p className="month-details-empty">На этот день доступность не опубликована. Откройте свободные даты, чтобы получать заявки.</p>}
        {manageHref ? <a className="btn secondary month-manage-action" href={manageHref} onClick={openManage}>Управлять датами <span aria-hidden="true">＋</span></a> : null}
        <p className="month-timezone">Время указано по Москве</p>
      </aside>
    </div> : <div className="calendar-agenda" aria-live="polite">
      {monthEntries.length ? monthEntries.map(entry => <article key={entry.id}><span className={`calendar-status-pill status-${entry.status}`}>{CALENDAR_STATUS_LABELS[entry.status] || entry.status}</span><div><strong>{entry.label || formatWhen(entry.starts_at)}</strong><p>{entry.label ? `${formatWhen(entry.starts_at)} — ` : "До "}{formatWhen(entry.ends_at)}</p></div></article>) : <p className="workspace-soft-empty">В этом месяце нет опубликованных слотов.</p>}
    </div>}
  </section>;
}
