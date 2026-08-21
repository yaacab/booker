/** Только внутренние пути. Иначе — кабинет. */
export function safeNext(raw: string | null | undefined, fallback = "/cabinet"): string {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("://")) return fallback;
  if (raw.startsWith("/login")) return fallback;
  return raw;
}

export function loginHref(next?: string): string {
  const path = safeNext(next, "/cabinet");
  if (path === "/cabinet") return "/login";
  return `/login?next=${encodeURIComponent(path)}`;
}
