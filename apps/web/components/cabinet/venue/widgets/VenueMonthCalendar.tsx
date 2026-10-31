"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CALENDAR_STATUS_LABELS, entriesOnDay, moscowDay, type CalendarEntry } from "@/lib/calendarMonth";
import { formatClock } from "@/lib/format";
import { MonthCalendar } from "../../MonthCalendar";
import { CabinetIcon } from "../../CabinetIcon";

type HallSlot = CalendarEntry & { hall: string };

export function VenueMonthCalendar({ venueId, hallNames = [] }: { venueId: string; hallNames?: string[] }) {
  const [slots, setSlots] = useState<HallSlot[]>([]);
  const [hall, setHall] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"week" | "month">("week");
  const [showHolds, setShowHolds] = useState(true);
  const [anchor, setAnchor] = useState(() => moscowDay(new Date().toISOString()));
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<{ slots: HallSlot[] }>(`/venues/${encodeURIComponent(venueId)}`).then(data => {
      if (active) { setSlots(data.slots || []); setHall(""); }
    }).catch(() => { if (active) setError("Не удалось загрузить календарь залов."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [venueId]);
  const halls = [...new Set([...hallNames, ...slots.map(slot => slot.hall)])].filter(Boolean);
  const visibleSlots = slots.filter(slot => (!hall || slot.hall === hall) && (showHolds || !["held", "hold"].includes(slot.status))).map(slot => ({ ...slot, label: slot.hall }));
  const anchorDate = new Date(`${anchor}T12:00:00Z`);
  const mondayOffset = (anchorDate.getUTCDay() + 6) % 7;
  const days = Array.from({ length: 7 }, (_, index) => new Date(Date.UTC(anchorDate.getUTCFullYear(), anchorDate.getUTCMonth(), anchorDate.getUTCDate() - mondayOffset + index, 12)).toISOString().slice(0, 10));
  function moveWeek(offset: number) { setAnchor(new Date(Date.UTC(anchorDate.getUTCFullYear(), anchorDate.getUTCMonth(), anchorDate.getUTCDate() + offset * 7, 12)).toISOString().slice(0, 10)); }

  return <section className="venue-calendar-panel" aria-label="Календарь залов">
    {loading ? <p role="status" className="workspace-soft-empty">Загружаем календарь…</p> : error ? <p role="alert">{error}</p> : <>
      <div className="venue-calendar-toolbar">
        {view === "week" ? <div className="month-navigation"><button type="button" className="secondary month-arrow" aria-label="Предыдущая неделя" onClick={() => moveWeek(-1)}>‹</button><strong aria-live="polite">{new Date(`${days[0]}T12:00:00Z`).toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" })} — {new Date(`${days[6]}T12:00:00Z`).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}</strong><button type="button" className="secondary month-arrow" aria-label="Следующая неделя" onClick={() => moveWeek(1)}>›</button><button type="button" className="secondary" onClick={() => setAnchor(moscowDay(new Date().toISOString()))}>Сегодня</button></div> : <strong>Занятость залов</strong>}
        <div className="calendar-view-switch" role="group" aria-label="Вид календаря залов"><button type="button" aria-pressed={view === "week"} onClick={() => setView("week")}>Неделя</button><button type="button" aria-pressed={view === "month"} onClick={() => setView("month")}>Месяц</button></div>
      </div>
      {view === "month" ? <MonthCalendar entries={visibleSlots} label="Календарь залов по месяцам" manageHref="#calendar-manage" /> : <div className="venue-week-scroll"><table className="venue-week-table"><caption className="sr-only">Опубликованные слоты по залам. Время московское.</caption><thead><tr><th scope="col">Залы</th>{days.map(day => <th scope="col" key={day}><strong>{new Date(`${day}T12:00:00Z`).toLocaleDateString("ru-RU", { weekday: "short", timeZone: "UTC" })}</strong><span>{new Date(`${day}T12:00:00Z`).toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" })}</span></th>)}</tr></thead><tbody>
        {(hall ? halls.filter(name => name === hall) : halls).map(name => <tr key={name}><th scope="row"><span className="venue-hall-icon"><CabinetIcon name="building" /></span><strong>{name}</strong></th>{days.map(day => <td key={day}>{entriesOnDay(visibleSlots.filter(slot => slot.hall === name), day).map(slot => <div key={slot.id} className={`venue-week-slot status-${slot.status}`}><strong>{CALENDAR_STATUS_LABELS[slot.status] || slot.status}</strong><span>{formatClock(slot.starts_at)} — {formatClock(slot.ends_at)}</span></div>)}</td>)}</tr>)}
        {!halls.length ? <tr><td colSpan={8} className="workspace-soft-empty">Добавьте первый зал, чтобы планировать его доступность.</td></tr> : null}
      </tbody></table></div>}
      <footer className="venue-calendar-footer"><div className="month-legend"><span><i className="status-open" />Свободно</span><span><i className="status-booked" />Бронь</span><span><i className="status-held" />Удержание</span><span><i className="status-busy" />Занято</span></div><label className="calendar-holds-toggle"><input type="checkbox" checked={showHolds} onChange={event => setShowHolds(event.target.checked)} />Показывать удержания</label><label className="venue-hall-filter"><span className="sr-only">Фильтр по залам</span><select value={hall} onChange={event => setHall(event.target.value)}><option value="">Все залы</option>{halls.map(name => <option key={name} value={name}>{name}</option>)}</select></label></footer>
      <p className="month-timezone">Пустая ячейка — нет опубликованных слотов. Время по Москве.</p>
    </>}
  </section>;
}
