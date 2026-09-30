import { ApiError } from "./api";

/** A changed draft is a new command; retries of identical data keep the same server key. */
export async function eventCommandKey(seed: string, payload: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify([seed, payload]));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function eventCommandSeed(storageKey: string): string {
  const saved = sessionStorage.getItem(storageKey);
  if (saved) return saved;
  const seed = crypto.randomUUID();
  sessionStorage.setItem(storageKey, seed);
  return seed;
}

export function eventCommandError(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) return "Проверьте дату, окончание, число гостей и бюджет. Число гостей и сумма должны быть целыми неотрицательными значениями; гостей — хотя бы один.";
  if (error instanceof Error && /[А-Яа-яЁё]/.test(error.message) && !error.message.startsWith("{") && !error.message.startsWith("[")) return error.message;
  return "Не удалось завершить отправку. Повторите попытку: уже сохранённые заявки не будут созданы заново.";
}
