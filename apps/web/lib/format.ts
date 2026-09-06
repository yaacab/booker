const TZ = "Europe/Moscow";
/** Moscow has no DST since 2014; naive API datetimes are pilot wall clock in MSK. */
const MSK_OFFSET = "+03:00";

/**
 * Parse Booker API datetimes for display.
 * Naive ISO (no `Z`/offset) must be treated as Europe/Moscow wall time: Node on UTC
 * servers otherwise parses them as UTC while browsers in MSK use local time, which
 * desyncs SSR vs client text and throws React #418 on /search.
 */
export function parseBookerDate(iso: string): Date {
  const trimmed = iso.trim();
  if (!trimmed) return new Date(NaN);
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return new Date(`${trimmed}T00:00:00${MSK_OFFSET}`);
  }
  if (/([zZ]|[+-]\d{2}:?\d{2})$/.test(trimmed)) {
    return new Date(trimmed);
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(trimmed)) {
    return new Date(`${trimmed}${MSK_OFFSET}`);
  }
  return new Date(trimmed);
}

export function formatWhen(iso?: string | null): string {
  if (!iso) return "дата не указана";
  const d = parseBookerDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  }).format(d);
}

export function formatDay(iso: string): string {
  const d = parseBookerDate(iso);
  if (Number.isNaN(d.getTime())) return "дата не указана";
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: TZ,
  }).format(d);
}

export function formatClock(iso: string): string {
  const d = parseBookerDate(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  }).format(d);
}

export function moscowDate(iso: string): string {
  const d = parseBookerDate(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function moscowToday(): string {
  return moscowDate(new Date().toISOString());
}

export function money(n: number): string {
  // Normalize NBSP/NNBSP so SSR (Node ICU) and browsers never diverge on spaces.
  return new Intl.NumberFormat("ru-RU").format(n).replace(/[\u00a0\u202f]/g, " ") + " ₽";
}

/** Русская плюрализация: pluralRu(1, "гость", "гостя", "гостей"). */
export function pluralRu(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(Math.trunc(n)) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (last > 1 && last < 5) return few;
  if (last === 1) return one;
  return many;
}

export function guestsLabel(n: number): string {
  return `${n} ${pluralRu(n, "гость", "гостя", "гостей")}`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = (parts[0]?.[0] || "") + (parts[1]?.[0] || "");
  return letters.toUpperCase() || "?";
}

export function holdRemaining(iso: string): string {
  const ms = parseBookerDate(iso).getTime() - Date.now();
  if (Number.isNaN(ms) || ms <= 0) return "hold истёк";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `осталось ${h} ч ${m} мин`;
  if (m > 0) return `осталось ${m} мин ${s} с`;
  return `осталось ${s} с`;
}
