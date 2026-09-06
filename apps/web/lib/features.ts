/** Feature flags for gradual rollout. Old flows stay available when flags are off. */

export function isEventStudioMapV1(searchParams?: URLSearchParams | null): boolean {
  const fromParams = searchParams?.get("event_studio_map_v1");
  if (fromParams === "0") return false;
  if (fromParams === "1") return true;
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search).get("event_studio_map_v1");
    if (q === "0") return false;
    if (q === "1") return true;
  }
  return true;
}
