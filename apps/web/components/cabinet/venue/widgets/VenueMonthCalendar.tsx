"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CalendarEntry } from "@/lib/calendarMonth";
import { MonthCalendar } from "../../MonthCalendar";
import { DashboardWidget } from "../../DashboardWidget";

type HallSlot = CalendarEntry & { hall: string };

export function VenueMonthCalendar({ venueId }: { venueId: string }) {
  const [slots, setSlots] = useState<HallSlot[]>([]);
  const [hall, setHall] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<{ slots: HallSlot[] }>(`/venues/${encodeURIComponent(venueId)}`).then(data => {
      if (active) { setSlots(data.slots || []); setHall(""); }
    }).catch(() => { if (active) setError("Не удалось загрузить календарь залов."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [venueId]);
  const halls = [...new Set(slots.map(slot => slot.hall))];
  return <DashboardWidget title="Календарь залов" hint="Опубликованные слоты площадки" accent="venue" span="full">
    {loading ? <p role="status">Загружаем календарь…</p> : error ? <p role="alert">{error}</p> : <>
      <label>Зал<select value={hall} onChange={e => setHall(e.target.value)}><option value="">Все залы</option>{halls.map(name => <option key={name} value={name}>{name}</option>)}</select></label>
      <MonthCalendar entries={hall ? slots.filter(slot => slot.hall === hall) : slots} label="Календарь залов" />
    </>}
  </DashboardWidget>;
}
