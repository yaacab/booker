export const INDEXABLE_STATIC_PATHS = [
  "/",
  "/search",
  "/faq",
  "/legal",
  "/legal/offer",
  "/legal/privacy",
  "/legal/disputes",
  "/legal/cookies",
  "/legal/suppliers",
  "/legal/cancellation",
] as const;

export function canonicalSiteUrl(value = process.env.NEXT_PUBLIC_SITE_URL): string {
  const candidate = (value || "https://bukergo.ru").trim().replace(/\/+$/, "");
  const url = new URL(candidate);
  return url.origin;
}

export function publicProfilePath(type: "artist" | "venue", id: string): string {
  const segment = type === "artist" ? "artists" : "venues";
  return `/${segment}/${encodeURIComponent(id)}`;
}
