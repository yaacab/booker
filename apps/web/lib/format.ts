const TZ = "Europe/Moscow";

export function formatWhen(iso?: string | null): string {
  if (!iso) return "дата не указана";
  const d = new Date(iso);
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
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: TZ,
  }).format(new Date(iso));
}

export function formatClock(iso: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  }).format(new Date(iso));
}

export function moscowDate(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

export function moscowToday(): string {
  return moscowDate(new Date().toISOString());
}

export function money(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n) + " ₽";
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = (parts[0]?.[0] || "") + (parts[1]?.[0] || "");
  return letters.toUpperCase() || "?";
}

export function holdRemaining(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms) || ms <= 0) return "hold истёк";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `осталось ${h} ч ${m} мин`;
  if (m > 0) return `осталось ${m} мин ${s} с`;
  return `осталось ${s} с`;
}
