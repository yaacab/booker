import { api } from "./api";

/** Session-scoped random key, no contact data or cross-device identity. */
export function observeDiscovery(target_type: "artist" | "venue", target_id: string, kind: "impression" | "profile_view") {
  try {
    if (navigator.doNotTrack === "1") return;
    const key = "booker.discovery.session";
    let visitor_id = sessionStorage.getItem(key);
    if (!visitor_id) { visitor_id = crypto.randomUUID(); sessionStorage.setItem(key, visitor_id); }
    void api("/discovery/signals", { method: "POST", keepalive: true, body: JSON.stringify({ target_type, target_id, kind, visitor_id }) }).catch(() => {});
  } catch { /* A blocked browser storage must not interrupt discovery. */ }
}
