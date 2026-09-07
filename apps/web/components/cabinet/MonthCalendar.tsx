"use client";

import { useId, useMemo, useState } from "react";
import { entriesOnDay, monthCells, moscowDay, type CalendarEntry } from "@/lib/calendarMonth";
import { formatWhen } from "@/lib/format";

const LABELS: Record<string, string> = { open: "Свободен", held: "Удержание", booked: "Забронирован", busy: "Занят", blocked: "Недоступен", cancelled: "Отменён" };

export function MonthCalendar({ entries, label = "Календарь доступности" }: { entries: CalendarEntry[]; label?: string }) {
  const today = moscowDay(new Date().toISOString());
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(() => new Date(`${today.slice(0,7)}-01T12:00:00Z`));
  const detailsId = useId();
  const cells = useMemo(() => monthCells(month.getUTCFullYear(), month.getUTCMonth()), [month]);
  const dayEntries = useMemo(() => new Map(cells.map(day => [day, entriesOnDay(entries, day)])), [cells, entries]);
  const visibleMonth = month.toISOString().slice(0,7);
  const selectedEntries = dayEntries.get(selected) || entriesOnDay(entries, selected);
  function moveMonth(offset: number) {
    setMonth(new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + offset, 1, 12)));
  }
  return <section className="month-calendar" aria-label={label}>
    <div className="month-toolbar">
      <button type="button" className="secondary" onClick={() => { setSelected(today); setMonth(new Date(`${today.slice(0,7)}-01T12:00:00Z`)); }}>Сегодня</button>
      <button type="button" className="secondary" aria-label="Предыдущий месяц" onClick={() => moveMonth(-1)}>‹</button>
      <h3 aria-live="polite">{month.toLocaleDateString("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" })}</h3>
      <button type="button" className="secondary" aria-label="Следующий месяц" onClick={() => moveMonth(1)}>›</button>
    </div>
    <div className="month-layout">
      <div>
        <div className="month-weekdays" aria-hidden="true">{["Пн","Вт","Ср","Чт","Пт","Сб","Вс"].map(day => <span key={day}>{day}</span>)}</div>
        <div className="month-days">
          {cells.map(day => {
            const items = dayEntries.get(day) || [];
            const hasBusy = items.some(item => item.status !== "open");
            const tone = items.length ? hasBusy ? "occupied" : "available" : "unknown";
            return <button type="button" key={day} className={`month-day ${tone}${day.startsWith(visibleMonth) ? "" : " adjacent"}`}
              aria-label={`${day}: ${items.length ? `слотов ${items.length}, ${hasBusy ? "есть занятость" : "свободен"}` : "Нет опубликованных слотов"}`}
              aria-pressed={day === selected} aria-current={day === today ? "date" : undefined} aria-controls={detailsId}
              onClick={() => setSelected(day)}>
              <strong>{Number(day.slice(-2))}</strong><span>{items.length ? hasBusy ? "Есть занятость" : "Свободен" : "—"}</span>
            </button>;
          })}
        </div>
        <p className="month-legend">Свободен — есть открытый слот. «—» — доступность не опубликована.</p>
      </div>
      <aside className="month-details" id={detailsId} aria-live="polite">
        <h3>{new Date(`${selected}T12:00:00+03:00`).toLocaleDateString("ru-RU", {day:"numeric",month:"long",timeZone:"Europe/Moscow"})}</h3>
        {selectedEntries.length ? <ul>{selectedEntries.map(entry => <li key={entry.id}><strong>{LABELS[entry.status] || entry.status}</strong><p>{formatWhen(entry.starts_at)} — {formatWhen(entry.ends_at)}</p></li>)}</ul> : <p>На этот день нет опубликованных слотов. Управляйте доступностью в настройках календаря.</p>}
      </aside>
    </div>
  </section>;
}
