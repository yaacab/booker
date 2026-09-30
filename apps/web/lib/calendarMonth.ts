import { parseBookerDate } from "./format";

export type CalendarEntry = { id: string; starts_at: string; ends_at: string; status: string; label?: string };

export const CALENDAR_STATUS_LABELS: Record<string, string> = {
  open: "Свободен", held: "Удержание", hold: "Удержание", booked: "Забронирован", busy: "Занят", blocked: "Недоступен", cancelled: "Отменён",
};

/** A cancelled interval does not override active availability on the same day. */
export function calendarDayStatus(entries: CalendarEntry[]): string {
  for (const status of ["booked", "busy", "blocked", "held", "hold", "open"]) {
    if (entries.some(entry => entry.status === status)) return status;
  }
  return entries[0]?.status || "unknown";
}

export function moscowDay(value: string): string {
  const date = parseBookerDate(value);
  if (!date || Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

/** Полуоткрытый интервал: слот, окончившийся в полночь, не занимает следующий день. */
export function entriesOnDay(entries: CalendarEntry[], day: string): CalendarEntry[] {
  const start = new Date(`${day}T00:00:00+03:00`).getTime();
  return entries.filter(entry => {
    const from = parseBookerDate(entry.starts_at)?.getTime();
    const to = parseBookerDate(entry.ends_at)?.getTime();
    return from != null && to != null && from < start + 86400000 && to > start;
  });
}

export function monthCells(year: number, month: number): string[] {
  const first = new Date(Date.UTC(year, month, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => new Date(Date.UTC(year, month, i - offset + 1)).toISOString().slice(0, 10));
}
