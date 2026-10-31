/* Букер · motion presets shared by every scene after the Scene 01 intro.
   Durations follow BK-DESIGN-TYPE-017. Decorative motion never gates
   navigation, form submission or API calls. */

export const MOTION = {
  press: 150, // button / card response 120–180ms
  field: 220, // field / paper panel appearance 180–250ms
  related: 550, // related-card transformation 500–650ms
  cover: 600, // catalog photo → profile cover
  reduced: 140, // reduced-motion fade, ≤150ms
  tiltMaxDeg: 5, // hover tilt 4–6°
  perspective: 1200,
} as const;

export const EASE = {
  /* matches Scene 01 E_OUT (0.16,1,0.3,1) — long, soft settle */
  settle: "cubic-bezier(0.16, 1, 0.3, 1)",
  /* matches Scene 01 E_IO */
  inOut: "cubic-bezier(0.65, 0, 0.35, 1)",
  press: "cubic-bezier(0.2, 0, 0, 1)",
} as const;

export function prefersReducedMotion(win: Pick<Window, "matchMedia"> | undefined = typeof window === "undefined" ? undefined : window): boolean {
  try { return Boolean(win?.matchMedia?.("(prefers-reduced-motion: reduce)").matches); } catch { return false; }
}

/* ---------- shared-element handoff between documents/routes ---------- */

export type HandoffRect = { x: number; y: number; w: number; h: number };
export type Handoff<T extends Record<string, string> = Record<string, string>> = { rect: HandoffRect; at: number; data: T };
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const KEY = (channel: string) => `booker.handoff.${channel}`;
/* Handoffs are only honoured right after the action that created them; a stale
   entry (Back/Forward, a new tab, a slow API) simply falls back to a plain fade. */
export const HANDOFF_MAX_AGE_MS = 4000;

function storage(): StorageLike | null {
  try { return typeof window === "undefined" ? null : window.sessionStorage; } catch { return null; }
}

export function saveHandoff(channel: string, rect: Pick<DOMRect, "left" | "top" | "width" | "height">, data: Record<string, string>, store: StorageLike | null = storage(), now = Date.now()): void {
  if (!store) return;
  const value: Handoff = { rect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height }, at: now, data };
  try { store.setItem(KEY(channel), JSON.stringify(value)); } catch { /* storage denied: navigation still works */ }
}

/** Reads and always clears the handoff, so it is consumed at most once. */
export function takeHandoff(channel: string, match: (data: Record<string, string>) => boolean = () => true, store: StorageLike | null = storage(), now = Date.now(), maxAge = HANDOFF_MAX_AGE_MS): Handoff | null {
  if (!store) return null;
  let raw: string | null = null;
  try { raw = store.getItem(KEY(channel)); store.removeItem(KEY(channel)); } catch { return null; }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Handoff;
    const r = parsed?.rect;
    if (!r || ![r.x, r.y, r.w, r.h, parsed.at].every(Number.isFinite) || r.w <= 0 || r.h <= 0) return null;
    if (now - parsed.at < 0 || now - parsed.at > maxAge) return null;
    if (!match(parsed.data || {})) return null;
    return parsed;
  } catch { return null; }
}

/** FLIP transform that maps the element's final box onto the remembered one. */
export function flipKeyframes(from: HandoffRect, to: HandoffRect): Keyframe[] {
  const sx = from.w / to.w, sy = from.h / to.h;
  const dx = from.x - to.x, dy = from.y - to.y;
  return [
    { transformOrigin: "0 0", transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, borderRadius: "18px" },
    { transformOrigin: "0 0", transform: "translate(0, 0) scale(1, 1)" },
  ];
}

/** Plays the shared-element arrival. Returns the Animation (or null when skipped). */
export function playArrival(el: HTMLElement, from: HandoffRect | null, duration: number = MOTION.related, opts: { depth?: boolean } = { depth: true }): Animation | null {
  if (typeof el.animate !== "function") return null;
  if (prefersReducedMotion() || !from) {
    return el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: MOTION.reduced, easing: "linear" });
  }
  const b = el.getBoundingClientRect();
  const to = { x: b.left, y: b.top, w: b.width, h: b.height };
  if (to.w <= 0 || to.h <= 0) return null;
  /* Very distant/oversized jumps read as a camera fly-through; keep it a soft settle instead. */
  if (Math.abs(from.w / to.w) > 6 || Math.abs(from.h / to.h) > 6) {
    return el.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: MOTION.field, easing: EASE.settle });
  }
  const flip = el.animate(flipKeyframes(from, to), { duration, easing: EASE.settle });
  if (opts.depth) {
    /* volume: the paper lifts toward the viewer and turns slightly while travelling,
       then lands flat. Added on top of the FLIP; light stays top-left. */
    const phone = typeof window !== "undefined" && window.innerWidth < 700;
    const turn = phone ? 4 : 9, lift = phone ? 14 : 32;
    try {
      el.animate([
        { transform: "perspective(1200px)", boxShadow: "6px 14px 30px -18px #3a281459" },
        { offset: 0.42, transform: `perspective(1200px) translateZ(${lift}px) rotateY(${-turn}deg) rotateX(${turn * 0.45}deg)`, boxShadow: "18px 34px 60px -24px #3a281470" },
        { transform: "perspective(1200px)", boxShadow: "6px 14px 30px -18px #3a281459" },
      ], { duration, easing: EASE.inOut, composite: "add" });
    } catch { /* composite unsupported: plain FLIP */ }
  }
  return flip;
}
