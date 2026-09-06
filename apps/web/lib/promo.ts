import { apiBase } from "@/lib/api";

export type ProfileKind = "artist" | "venue";
export type PromoMedium = "link" | "qr" | "social";

/** Canonical utm_source for organic supply share links (no PII). */
export const PROMO_UTM_SOURCE = "booker_share";

const CAMPAIGN: Record<ProfileKind, string> = {
  artist: "artist_profile",
  venue: "venue_profile",
};

export type ShareUrlOptions = {
  medium?: PromoMedium;
  hallId?: string;
  tariffId?: string;
};

export function publicSiteBase(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru").replace(/\/$/, "");
}

export function profilePath(kind: ProfileKind, id: string): string {
  return kind === "artist" ? `/artists/${encodeURIComponent(id)}` : `/venues/${encodeURIComponent(id)}`;
}

export function buildShareUrl(kind: ProfileKind, id: string, options: ShareUrlOptions = {}): string {
  const medium = options.medium ?? "link";
  const params = new URLSearchParams({
    utm_source: PROMO_UTM_SOURCE,
    utm_medium: medium,
    utm_campaign: CAMPAIGN[kind],
  });
  if (options.hallId) params.set("hall", options.hallId);
  if (options.tariffId) params.set("tariff", options.tariffId);
  return `${publicSiteBase()}${profilePath(kind, id)}?${params.toString()}`;
}

export type PromoAttribution = {
  source: string;
  medium: string;
  campaign: string;
  hallId: string | null;
  tariffId: string | null;
};

export function parsePromoAttribution(raw: string | URLSearchParams | null | undefined): PromoAttribution | null {
  const params =
    raw instanceof URLSearchParams
      ? raw
      : new URLSearchParams(typeof raw === "string" ? raw.replace(/^\?/, "") : "");
  const source = params.get("utm_source");
  if (source !== PROMO_UTM_SOURCE) return null;
  const medium = params.get("utm_medium");
  const campaign = params.get("utm_campaign");
  if (!medium || !campaign) return null;
  return {
    source,
    medium,
    campaign,
    hallId: params.get("hall"),
    tariffId: params.get("tariff"),
  };
}

/** External QR image URL — no npm deps (qrserver public API). */
export function qrCodeImageUrl(data: string, size = 240): string {
  const side = Math.min(Math.max(size, 120), 512);
  return `https://api.qrserver.com/v1/create-qr-code/?size=${side}x${side}&data=${encodeURIComponent(data)}&margin=8`;
}

export type PromoEventName =
  | "promo.share.view"
  | "promo.profile.open"
  | "promo.link.copy"
  | "promo.qr.display";

export type PromoEventPayload = {
  profile_kind: ProfileKind;
  profile_id: string;
  medium?: string;
  source?: string;
};

export function trackPromoEvent(name: PromoEventName, payload: PromoEventPayload): void {
  if (typeof window === "undefined") return;
  void fetch(`${apiBase()}/promo/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...payload }),
    keepalive: true,
  }).catch(() => {});
}
