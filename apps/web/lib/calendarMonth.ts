import { parseBookerDate } from "./format";

export type CalendarEntry = { id: string; starts_at: string; ends_at: string; status: string };

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
