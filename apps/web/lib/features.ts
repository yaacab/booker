/** Feature flags for gradual rollout. Old flows stay available when flags are off. */

export function isEventStudioMapV1(searchParams?: URLSearchParams | null): boolean {
  if (searchParams?.get("event_studio_map_v1") === "1") return true;
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search);
    if (q.get("event_studio_map_v1") === "1") return true;
  }
  return process.env.NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 === "1";
}
