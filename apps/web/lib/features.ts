/** Feature flags for gradual rollout. Classic Event Studio wizard is the default. */

/**
 * Event Studio Map v1.
 * Precedence: explicit query `event_studio_map_v1=0|1` → `NEXT_PUBLIC_EVENT_STUDIO_MAP_V1` → default OFF.
 *
 * `?event_studio_map_v1=0|1` switches UI for that URL only (not a site-wide rollback).
 * Global rollback: set env to `0`/unset, rebuild and redeploy web (`NEXT_PUBLIC_*` is build-time).
 * Do not change production without owner OK.
 */
export function isEventStudioMapV1(searchParams?: URLSearchParams | null): boolean {
  const fromParams = searchParams?.get("event_studio_map_v1");
  if (fromParams === "0") return false;
  if (fromParams === "1") return true;
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search).get("event_studio_map_v1");
    if (q === "0") return false;
    if (q === "1") return true;
  }
  const env = process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1;
  if (env === "1" || env === "true") return true;
  if (env === "0" || env === "false") return false;
  return false;
}
