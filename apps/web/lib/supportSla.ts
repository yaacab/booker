export const SUPPORT_HOURS_TEXT = "Рабочее окно поддержки: ежедневно 10:00–22:00 МСК.";
export const SUPPORT_TARGET_TEXT = "Для срочных обращений показываем расчётную цель первого ответа; это не гарантия.";

export function formatSupportDeadline(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const value = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    hourCycle: "h23", timeZone: "Europe/Moscow",
  }).format(date);
  return `${value} МСК`;
}

export function supportDeadlineLabel(
  iso: string, status: string, reopenedAt: string | null | undefined, hasOperatorResponse: boolean,
): string {
  const formatted = formatSupportDeadline(iso);
  if (!formatted) return "";
  const historical = status === "closed" || Boolean(reopenedAt) || hasOperatorResponse;
  return historical
    ? ` · расчётная цель первого ответа была до ${formatted}; новый срок не назначен`
    : ` · цель первого ответа до ${formatted}`;
}
