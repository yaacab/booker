"use client";
import {createContext,useCallback,useContext,useEffect,useLayoutEffect,useMemo,useReducer,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import type {EventStudioMapProps} from './EventStudioMap';
import {toVisual,fromVisual,type VisualDraft} from './v5Adapter';
import {DateTimeField,formatISODate} from './V5DateTimeField';
import './flexible-event-v5.css';
const placeholder='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="600" height="400"%3E%3Crect width="600" height="400" fill="%23e7ddce"/%3E%3C/svg%3E';
// Instance-local catalogue: no demo identities, invented prices or cross-instance mutable state.
function createScene(){
let live:EventStudioMapProps;
const AVATARS = [
  "1500648767791-00dcc994a43e",
  "1494790108377-be9c29b29330",
  "1438761681033-6461ffad8d80",
  "1472099645785-5658abf4ff4e",
].map((id) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=96&h=96&q=70`);
const f2 = (n: number) => (Math.round(n * 100) / 100).toString();
const MOTION = {
  micro: 180, std: 380, layout: 720, cine: 1150,
  settle: "cubic-bezier(0.16, 1, 0.3, 1)",
  sym: "cubic-bezier(0.65, 0, 0.35, 1)",
  stagger: 60,
};
const prefersReduced = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
interface Box { x: number; y: number; w: number; h: number }
const boxOf = (el: Element | null | undefined): Box | null => {
  if (!el) return null;
  const b = el.getBoundingClientRect();
  if (b.width < 1 || b.height < 1) return null;
  return { x: b.left, y: b.top, w: b.width, h: b.height };
};
function projection(from: Box, to: Box, radiusFrom: number, radiusTo: number, ps: number) {
  const s = Math.max(from.w / to.w, from.h / to.h);
  const lw = to.w / ps, lh = to.h / ps;
  const ix = Math.max(0, (lw - from.w / (s * ps)) / 2), iy = Math.max(0, (lh - from.h / (s * ps)) / 2);
  const dx = (from.x + from.w / 2 - (to.x + to.w / 2)) / ps;
  const dy = (from.y + from.h / 2 - (to.y + to.h / 2)) / ps;
  return {
    s, dx, dy,
    clip: `inset(${f2(iy)}px ${f2(ix)}px round ${f2(radiusFrom / (s * ps))}px)`,
    clipEnd: `inset(0px 0px round ${f2(radiusTo / ps)}px)`,
  };
}
interface FlipOpts {
  dur?: number; delay?: number; ease?: string; rFrom?: number; rTo?: number;
  arc?: number; fadeIn?: boolean; ps?: number; onDone?: () => void;
}
function flipFrom(el: HTMLElement, from: Box, o: FlipOpts = {}) {
  const to = boxOf(el);
  if (!to) { o.onDone?.(); return null; }
  const ps = o.ps ?? (el.offsetWidth ? to.w / el.offsetWidth : 1);
  const dur = o.dur ?? MOTION.layout;
  if (prefersReduced()) {
    const a = el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, delay: o.delay ?? 0, easing: "linear", fill: "backwards" });
    a.onfinish = () => o.onDone?.();
    return a;
  }
  const p = projection(from, to, o.rFrom ?? 12, o.rTo ?? 12, ps);
  const frames: Keyframe[] = [];
  const N = o.arc ? 6 : 1;
  for (let k = 0; k <= N; k++) {
    const u = k / N;
    // quadratic arc: the object travels along a soft curve (the gold thread), never a straight hop
    const bend = o.arc ? Math.sin(Math.PI * u) * o.arc : 0;
    const len = Math.hypot(p.dx, p.dy) || 1;
    const nx = -p.dy / len, ny = p.dx / len;
    const x = p.dx * (1 - u) + nx * bend, y = p.dy * (1 - u) + ny * bend;
    const sc = Math.pow(p.s, 1 - u);
    const fr: Keyframe = { offset: u, transform: `translate(${f2(x)}px, ${f2(y)}px) scale(${sc.toFixed(4)})` };
    if (k === 0) fr.clipPath = p.clip;
    if (k === N) fr.clipPath = p.clipEnd;
    if (o.fadeIn && k === 0) fr.opacity = 0;
    if (o.fadeIn && k === 1) fr.opacity = 1;
    frames.push(fr);
  }
  // fill clip keyframes between ends (WAAPI needs the property on first and last frames only)
  el.style.willChange = "transform, clip-path";
  const a = el.animate(frames, { duration: dur, delay: o.delay ?? 0, easing: o.ease ?? MOTION.settle, fill: "backwards" });
  a.onfinish = () => { el.style.willChange = ""; o.onDone?.(); };
  a.oncancel = () => { el.style.willChange = ""; };
  return a;
}
function flyTo(el: HTMLElement, to: Box, o: FlipOpts & { fadeOut?: boolean } = {}) {
  const from = boxOf(el);
  if (!from) { o.onDone?.(); return null; }
  const ps = o.ps ?? (el.offsetWidth ? from.w / el.offsetWidth : 1);
  if (prefersReduced()) {
    const a = el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, delay: o.delay ?? 0, fill: "forwards" });
    a.onfinish = () => o.onDone?.();
    return a;
  }
  const p = projection(to, from, o.rTo ?? 12, o.rFrom ?? 12, ps);
  const frames: Keyframe[] = [];
  const N = o.arc ? 6 : 1;
  for (let k = 0; k <= N; k++) {
    const u = k / N;
    const bend = o.arc ? Math.sin(Math.PI * u) * o.arc : 0;
    const len = Math.hypot(p.dx, p.dy) || 1;
    const nx = -p.dy / len, ny = p.dx / len;
    const fr: Keyframe = { offset: u, transform: `translate(${f2(p.dx * u + nx * bend)}px, ${f2(p.dy * u + ny * bend)}px) scale(${Math.pow(p.s, u).toFixed(4)})` };
    if (k === 0) fr.clipPath = p.clipEnd;
    if (k === N) { fr.clipPath = p.clip; if (o.fadeOut) fr.opacity = 0; }
    if (k === 0 && o.fadeOut) fr.opacity = 1;
    frames.push(fr);
  }
  el.style.willChange = "transform, clip-path";
  const a = el.animate(frames, { duration: o.dur ?? MOTION.layout, delay: o.delay ?? 0, easing: o.ease ?? MOTION.sym, fill: "forwards" });
  a.onfinish = () => { el.style.willChange = ""; o.onDone?.(); };
  return a;
}
interface Flight { from: Box; r?: number; arc?: number; dur?: number; delay?: number; id?: string }
interface FlightBus { put: (id: string, f: Flight) => void; take: (id: string) => Flight | null; peek: (id: string) => boolean }
const FlightCtx = createContext<FlightBus>({ put: () => {}, take: () => null, peek: () => false });
function useFlightBus(): FlightBus {
  const m = useRef(new Map<string, Flight>());
  return useMemo(() => ({
    put: (id, f) => { m.current.set(id, f); },
    take: (id) => { const f = m.current.get(id) ?? null; m.current.delete(id); return f; },
    peek: (id) => m.current.has(id),
  }), []);
}
function useArrive(ref: React.RefObject<HTMLElement | null>, id: string, dep: unknown, extra: FlipOpts = {}) {
  const bus = useContext(FlightCtx);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const f = bus.take(id);
    if (!f) return;
    flipFrom(el, f.from, { rFrom: f.r ?? 12, arc: f.arc, dur: f.dur, delay: f.delay, ...extra });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dep]);
}
function Roll({ value, className }: { value: string; className?: string }) {
  const prev = useRef(value);
  const [state, setState] = useState<{ cur: string; old: string; v: number; dir: 1 | -1 }>({ cur: value, old: value, v: 0, dir: 1 });
  useEffect(() => {
    if (prev.current === value) return;
    const a = parseFloat(prev.current.replace(/[^\d.]/g, "")) || 0, b = parseFloat(value.replace(/[^\d.]/g, "")) || 0;
    setState((s) => ({ cur: value, old: prev.current, v: s.v + 1, dir: b >= a ? 1 : -1 }));
    prev.current = value;
  }, [value]);
  const { cur, old, v, dir } = state;
  const L = Math.max(cur.length, old.length);
  const pc = cur.padStart(L, " "), po = old.padStart(L, " ");
  return (
    <span className={`jr-roll ${className ?? ""}`} aria-label={cur}>
      {Array.from({ length: L }, (_, i) => {
        const changed = v > 0 && pc[i] !== po[i];
        return (
          <span key={i} className="jr-roll-c" aria-hidden style={{ "--d": `${(L - 1 - i) * 40}ms` } as CSSProperties}>
            <span key={`n${v}`} className={changed ? (dir > 0 ? "in-up" : "in-down") : ""}>{pc[i] === " " ? " " : pc[i]}</span>
            {changed && <span key={`o${v}`} className={dir > 0 ? "out-up" : "out-down"}>{po[i] === " " ? " " : po[i]}</span>}
          </span>
        );
      })}
    </span>
  );
}
function MaskText({ lines, as = "h2", className, delay = 0 }: { lines: string[]; as?: "h1" | "h2" | "h3" | "p"; className?: string; delay?: number }) {
  const Tag = as;
  return (
    <Tag className={`jr-mask ${className ?? ""}`}>
      {lines.map((l, i) => (
        <span key={i} className="jr-mask-l"><span style={{ animationDelay: `${delay + i * 90}ms` }}>{l}</span></span>
      ))}
    </Tag>
  );
}
interface StageRect { left: number; top: number; width: number; height: number }
function Swap({ k, rect, exit = "step", children, className }: {
  k: string; rect: StageRect; exit?: "step" | "hold"; children: ReactNode; className?: string;
}) {
  type It = { k: string; node: ReactNode; rect: StageRect; exit: string };
  const [cur, setCur] = useState(k);
  const [olds, setOlds] = useState<It[]>([]);
  const lastRef = useRef<{ node: ReactNode; rect: StageRect }>({ node: children, rect });
  if (cur !== k) {
    // derived-state update during render (pure: reads the committed snapshot only)
    const gone: It = { k: cur, node: lastRef.current.node, rect: lastRef.current.rect, exit };
    setCur(k);
    setOlds((o) => [...o.filter((x) => x.k !== gone.k && x.k !== k), gone]);
  }
  useLayoutEffect(() => { if (cur === k) lastRef.current = { node: children, rect }; });
  useEffect(() => {
    if (!olds.length) return;
    const ids = olds.map((o) => window.setTimeout(() => setOlds((x) => x.filter((y) => y !== o)), o.exit === "hold" ? 1100 : 500));
    return () => ids.forEach((i) => window.clearTimeout(i));
  }, [olds]);
  const st = (r: StageRect): CSSProperties => ({ left: r.left, top: r.top, width: r.width, height: r.height });
  const items = [...olds.filter((o) => o.k !== k).map((o) => ({ ...o, leaving: true })), { k, node: children, rect, exit, leaving: false }];
  return (
    <>
      {items.map((o) => (
        <div key={o.k} className={`jr-swap ${o.leaving ? `is-leaving is-${o.exit}` : "is-entering"} ${className ?? ""}`}
          style={st(o.rect)} aria-hidden={o.leaving || undefined} inert={o.leaving || undefined}>
          {o.node}
        </div>
      ))}
    </>
  );
}
function useTimers() {
  const ids = useRef<number[]>([]);
  useEffect(() => () => { ids.current.forEach((i) => window.clearTimeout(i)); }, []);
  return useCallback((fn: () => void, ms: number) => { ids.current.push(window.setTimeout(fn, ms)); }, []);
}
const ph = (id: string, w = 900) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=72`;
const FORMATS = [
  { id: "private", title: "Частная вечеринка", note: "Друзья, музыка, свой ритм", img: ph("1470337458703-46ad1756a187") },
  { id: "wedding", title: "Свадьба", note: "Церемония и банкет", img: ph("1519167758481-83f550bb49b3") },
  { id: "corporate", title: "Корпоратив", note: "Команда и партнёры", img: ph("1492684223066-81342ee5ff30") },
  { id: "birthday", title: "День рождения", note: "Праздник с характером", img: ph("1528495612343-9ca9f4a4de28") },
  { id: "concert", title: "Концерт", note: "Сцена и зрители", img: ph("1470229722913-7c0e2dbbafd3") },
  { id: "other", title: "Другое", note: "Опишите свою идею", img: ph("1464366400600-7168b8af9bc3") },
];
type ArtistCat = "music" | "dj" | "host" | "show" | "media";
interface Artist {
  id: string; name: string; role: string; genre: string; cat: ArtistCat; price: number;
  free: boolean; img: string; pos?: string; city: string; rating: string;
}
const ARTISTS: Artist[] = [];
interface Venue { id: string; name: string; area: string; cap: number; minCap: number; price: number; free: boolean; img: string; kind: string }
const VENUES: Venue[] = [];
const RIDER = [
  { sec: "Звук", need: "Звук · система от 4 кВт", has: "L-Acoustics, 6 кВт", ok: true },
  { sec: "Техника", need: "DJ booth · 2×CDJ-3000, DJM-900", has: "DJ booth, Pioneer CDJ-3000", ok: true },
  { sec: "Гримерка", need: "Гримерка с зеркалом", has: "Отдельная гримерка", ok: true },
  { sec: "Трансфер", need: "Трансфер из аэропорта", has: "Требуется уточнение", ok: false },
];
const CITIES = ["Москва", "Санкт-Петербург", "Казань", "Сочи", "Екатеринбург"];
const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const rub = (n: number) => `${n.toLocaleString("ru-RU").replace(/ | /g, " ")} ₽`;
const plural = (n: number, one: string, few: string, many: string) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};
type JScene =
  | "intro" | "roles" | "registration" | "registrationComplete" | "home" | "eventEmail"
  | "eventOverview" | "eventFormat" | "eventDate" | "eventGuests"
  | "artistDiscovery" | "artistProfile" | "artistSelected"
  | "venueDiscovery" | "venueSelected" | "directRequest" | "directRequestReady"
  | "rider" | "budget" | "review" | "requestSent";
type PieceId = "format" | "date" | "guests" | "artist" | "venue" | "rider" | "budget";
const PIECE_ORDER: PieceId[] = ["format", "date", "guests", "artist", "venue", "rider", "budget"];
const PIECE_LABEL: Record<PieceId, string> = {
  format: "Формат", date: "Дата и город", guests: "Гости", artist: "Артист",
  venue: "Площадка", rider: "Райдер", budget: "Бюджет",
};
const SHARED_ID: Record<PieceId, string> = {
  format: "event-format", date: "event-date", guests: "event-guests", artist: "event-artist",
  venue: "event-venue", rider: "event-rider", budget: "event-budget",
};
type EventDraft = VisualDraft;
interface Identity { first: string; last: string; phone: string; email: string; contacts: string | null; city: string | null }
interface DirectRequest {
  kind: "artist" | "venue";
  id: string;
  date: string;
  time: string;
  city: string;
  address: string;
  guests: string;
  format: string;
  email: string;
  message: string;
}
interface Journey {
  scene: JScene;
  role: number;
  regStep: number;
  path: "event" | "artist" | "venue";
  identity: Identity;
  draft: EventDraft;
  rev: Record<PieceId, number>;
  profile: string | null;
  canvasIntro: boolean;
  pendingEventSelection: boolean;
  sentAt: number | null;
  directRequest: DirectRequest | null;
}
const EMPTY_DRAFT: EventDraft = { format: null, date: null, dateISO: null, time: null, city: null, guests: null, artists: [], venue: null, rider: null, budget: null };
const INIT_JOURNEY: Journey = {
  scene: "intro", role: 0, regStep: 0, path: "event",
  identity: { first: "", last: "", phone: "", email: "", contacts: null, city: null },
  draft: EMPTY_DRAFT,
  rev: { format: 0, date: 0, guests: 0, artist: 0, venue: 0, rider: 0, budget: 0 },
  profile: null, canvasIntro: false, pendingEventSelection: false, sentAt: null, directRequest: null,
};
type JAction =
  | { type: "scene"; scene: JScene }
  | { type: "choose"; role: number }
  | { type: "identity"; patch: Partial<Identity> }
  | { type: "regStep"; step: number }
  | { type: "startBuilder"; path: "event" | "artist" | "venue"; preserveSelection?: boolean }
  | { type: "canvasIntroDone" }
  | { type: "set"; piece: PieceId; patch: Partial<EventDraft>; next?: JScene }
  | { type: "removeArtist"; id: string }
  | { type: "openProfile"; id: string }
  | { type: "order"; kind: DirectRequest["kind"]; id: string }
  | { type: "requestDetails"; patch: Partial<Omit<DirectRequest, "kind" | "id">> }
  | { type: "send" }
  | { type: "newEvent" };
const filled = (d: EventDraft, p: PieceId) =>
  p === "format" ? !!d.format : p === "date" ? !!d.dateISO && !!d.time && !!d.city : p === "guests" ? d.guests !== null
    : p === "artist" ? (d.artists.length > 0 || !!d.artistsDeferred) : p === "venue" ? (!!d.venue || !!d.venueDeferred) : p === "rider" ? !!d.rider : d.budget !== null;
const SCENE_OF: Record<PieceId, JScene> = {
  format: "eventFormat", date: "eventDate", guests: "eventGuests", artist: "artistDiscovery",
  venue: "venueDiscovery", rider: "rider", budget: "budget",
};
function nextScene(d: EventDraft): JScene {
  for (const p of PIECE_ORDER) if (!filled(d, p)) return "eventOverview";
  return "review";
}
type CanvasMode = "hidden" | "center" | "side" | "corner" | "strip" | "review";
const CW = 540, CH = 660;
const CORE = { x: 270, y: 320, w: 172, h: 212 };
const SLOT: Record<PieceId, { x: number; y: number; w: number; h: number }> = {
  format: { x: 112, y: 108, w: 176, h: 118 },
  date: { x: 430, y: 100, w: 156, h: 86 },
  guests: { x: 462, y: 300, w: 150, h: 80 },
  artist: { x: 452, y: 480, w: 176, h: 132 },
  venue: { x: 262, y: 598, w: 204, h: 118 },
  rider: { x: 96, y: 474, w: 152, h: 82 },
  budget: { x: 88, y: 300, w: 160, h: 74 },
};
const STRIP_K = 0.46;
interface Frame { x: number; y: number; s: number }
interface JLayout {
  vw: number; vh: number; mobile: boolean; navH: number;
  frame: Frame; stage: StageRect; mode: CanvasMode;
}
function isMobile(vw: number, vh: number) { return vw < 760 || vw / vh < 0.95; }
function computeLayout(vw: number, vh: number, mode: CanvasMode): JLayout {
  const mobile = isMobile(vw, vh);
  const navH = mobile ? 56 : 66;
  const avail = vh - navH;
  const center = (): Frame => {
    const s = Math.min(1, (vw * (mobile ? 0.94 : 0.8)) / CW, (avail - (mobile ? 150 : 176)) / CH);
    return { x: (vw - CW * s) / 2, y: navH + (mobile ? 128 : 150), s };
  };
  if (mobile) {
    const frame = mode === "strip" ? { x: 0, y: navH, s: 1 } : center();
    const top = navH + 92;
    const stage = mode === "hidden" || mode === "review"
      ? { left: 0, top: navH, width: vw, height: avail }
      : { left: 16, top, width: vw - 32, height: vh - top - 8 };
    return { vw, vh, mobile, navH, frame, stage, mode };
  }
  const colW = Math.max(300, Math.min(500, vw * 0.34));
  const side = (): Frame => {
    const s = Math.min((colW - 20) / CW, (avail - 40) / CH, 1);
    return { x: 24 + (colW - 20 - CW * s) / 2, y: navH + (avail - CH * s) / 2, s };
  };
  const corner = (): Frame => {
    const s = Math.min(0.44, (avail * 0.5) / CH, 240 / CW);
    return { x: 22, y: navH + 14, s };
  };
  let frame: Frame, stage: StageRect;
  if (mode === "corner") {
    frame = corner();
    const left = 22 + CW * frame.s + 34;
    stage = { left, top: navH + 14, width: vw - left - 36, height: vh - navH - 30 };
  } else if (mode === "hidden") {
    frame = center();
    stage = { left: 0, top: navH, width: vw, height: avail };
  } else if (mode === "center") {
    frame = center();
    stage = { left: 40, top: navH + 24, width: vw - 80, height: 140 };
  } else {
    frame = side();
    const left = 24 + colW + 28;
    stage = mode === "review"
      ? { left: 36, top: navH + 10, width: vw - 72, height: vh - navH - 22 }
      : { left, top: navH + 22, width: vw - left - 44, height: vh - navH - 40 };
  }
  return { vw, vh, mobile, navH, frame, stage, mode };
}
function useViewport() {
  const [v, setV] = useState(() => ({ vw: window.innerWidth, vh: window.innerHeight }));
  useEffect(() => {
    let raf = 0;
    const on = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => setV({ vw: window.innerWidth, vh: window.innerHeight })); };
    window.addEventListener("resize", on);
    return () => { window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, []);
  return v;
}
function rayToRect(w: number, h: number, dx: number, dy: number) {
  const tx = dx !== 0 ? w / 2 / Math.abs(dx) : Infinity, ty = dy !== 0 ? h / 2 / Math.abs(dy) : Infinity;
  return Math.min(tx, ty);
}
function smoothPath(pts: { x: number; y: number }[], closed = false) {
  if (pts.length < 2) return "";
  const n = pts.length;
  const P = (i: number) => (closed ? pts[(i + n) % n] : pts[Math.max(0, Math.min(n - 1, i))]);
  let d = `M${f2(pts[0].x)} ${f2(pts[0].y)}`;
  const segs = closed ? n : n - 1;
  for (let i = 0; i < segs; i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    d += `C${f2(p1.x + (p2.x - p0.x) / 6)} ${f2(p1.y + (p2.y - p0.y) / 6)} ${f2(p2.x - (p3.x - p1.x) / 6)} ${f2(p2.y - (p3.y - p1.y) / 6)} ${f2(p2.x)} ${f2(p2.y)}`;
  }
  return d + (closed ? "Z" : "");
}
function spoke(id: PieceId) {
  const s = SLOT[id];
  let dx = CORE.x - s.x, dy = CORE.y - s.y;
  const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
  const a = rayToRect(s.w, s.h, dx, dy) + 6, b = rayToRect(CORE.w, CORE.h, -dx, -dy) + 8;
  return { x1: s.x + dx * a, y1: s.y + dy * a, x2: CORE.x - dx * b, y2: CORE.y - dy * b };
}
function artistById(id:string):Artist {return ARTISTS.find(a=>a.id===id)??{id,name:'Выбранный артист',role:'Данные уточняются',genre:'',cat:'music',price:0,free:false,img:placeholder,city:'',rating:''};}
function venueById(id: string | null) { return VENUES.find((v) => v.id === id) ?? (id ? {id,name:"Выбранная площадка",area:"Данные уточняются",cap:0,minCap:0,price:0,free:false,img:placeholder,kind:"Площадка"} : null); }
function formatById(id: string | null) { return FORMATS.find((f) => f.id === id) ?? null; }
const eventMonth = (d: EventDraft) => d.dateISO ? new Date(`${d.dateISO}T12:00:00`).toLocaleDateString("ru-RU", { month: "short" }).replace(".", "").toUpperCase() : "ОКТ";
const dateLong = (d: number) => `${d} ${MONTHS_GEN[9]} 2026`;
const eventDateText = (d: EventDraft) => d.dateISO
  ? `${formatISODate(d.dateISO)}${d.time ? `, ${d.time}` : ""}` : d.date ? dateLong(d.date) : "—";
function PieceBody({ id, d, status }: { id: PieceId; d: EventDraft; status?: string | null }) {
  switch (id) {
    case "format": {
      const f = formatById(d.format);
      return (<div className="jp jp-format">
        <div className="jp-photo"><img src={f?.img} alt="" draggable={false} /></div>
        <div className="jp-txt"><span className="jp-k">01 · Формат</span><b>{f?.title}</b></div>
      </div>);
    }
    case "date":
      return (<div className="jp jp-date">
        <div className="jp-cal"><b>{d.date}</b><span>{eventMonth(d)}</span></div>
        <div className="jp-txt"><span className="jp-k">02 · Когда и где</span><b>{eventDateText(d)}</b><em>{d.city}</em></div>
      </div>);
    case "guests":
      return (<div className="jp jp-guests">
        <div className="jp-txt"><span className="jp-k">03 · Гости</span><b><span className="jp-n">{d.guests === 200 ? "200+" : d.guests}</span> {plural(d.guests ?? 0, "гость", "гостя", "гостей")}</b></div>
        <div className="jp-av">{AVATARS.map((a) => <img key={a} src={a} alt="" draggable={false} />)}</div>
      </div>);
    case "artist": {
      const a = artistById(d.artists[0]);
      return (<div className="jp jp-artist">
        <div className="jp-photo"><img src={a.img} alt="" draggable={false} style={{ objectPosition: a.pos }} /></div>
        <div className="jp-txt"><span className="jp-k">04 · Артист</span><b>{d.artists.length ? a.name : "Подберём позже"}</b><em>{a.role} · {a.genre}</em></div>
        <span className={`jp-status${status ? " on" : ""}`}>{d.artists.length ? status ?? "Добавлен" : "Позже"}</span>
      </div>);
    }
    case "venue": {
      const v = venueById(d.venue);
      return (<div className="jp jp-venue">
        <img src={v?.img} alt="" draggable={false} />
        <div className="jp-txt"><span className="jp-k">05 · Площадка</span><b>{v?.name.toUpperCase()}</b><em>{v ? "Выбрана из каталога" : "Подберём позже"}</em></div>
      </div>);
    }
    case "rider":
      return (<div className="jp jp-rider">
        <svg viewBox="0 0 30 38" width="26" height="33" aria-hidden><path d="M2 2h18l8 8v26H2z M20 2v8h8" fill="none" stroke="currentColor" strokeWidth="1.2" /><path d="M7 17h15M7 22h15M7 27h10" stroke="currentColor" strokeWidth="1" /></svg>
        <div className="jp-txt"><span className="jp-k">06 · Райдер</span><b>Райдер</b><em>Сохранено требований: {d.rider?.requirements?.length ?? 0}</em></div>
      </div>);
    case "budget":
      return (<div className="jp jp-budget">
        <div className="jp-txt"><span className="jp-k">07 · Бюджет</span><b>до {rub(d.budget ?? 0)}</b><em>Предварительный ориентир</em></div>
      </div>);
  }
}
function Piece({ id, d, rev, mode, stripX, onOpen, status, interactive }: {
  id: PieceId; d: EventDraft; rev: number; mode: CanvasMode; stripX: number;
  onOpen: () => void; status?: string | null; interactive: boolean;
}) {
  const inner = useRef<HTMLButtonElement>(null);
  const s = SLOT[id];
  useArrive(inner, `piece-${id}`, rev);
  const tf = mode === "strip"
    ? `translate(${f2(stripX)}px, 12px) scale(${STRIP_K})`
    : `translate(${f2(s.x - s.w / 2)}px, ${f2(s.y - s.h / 2)}px)`;
  return (
    <div className={`jr-piece jr-piece-${id}`} data-piece={id} data-sid={SHARED_ID[id]} style={{ width: s.w, height: s.h, transform: tf }}>
      <button ref={inner} type="button" className="jr-piece-in" onClick={onOpen} tabIndex={interactive ? 0 : -1}
        aria-label={`${PIECE_LABEL[id]} — изменить`}>
        <PieceBody id={id} d={d} status={status} />
      </button>
    </div>
  );
}
function ArtistThumb({ id, k, mode, stripX }: { id: string; k: number; mode: CanvasMode; stripX: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useArrive(ref, `thumb-${id}`, id, { rFrom: 14, rTo: 40 });
  const a = artistById(id);
  const s = SLOT.artist;
  const tf = mode === "strip"
    ? `translate(${f2(stripX + (s.w - 12) * STRIP_K + k * 30)}px, ${f2(12 + 6)}px) scale(${STRIP_K * 1.1})`
    : `translate(${f2(s.x - s.w / 2 + 6 + k * 58)}px, ${f2(s.y + s.h / 2 + 14)}px)`;
  return (
    <div className="jr-thumb" style={{ transform: tf }} data-sid={`artist-${id}`}>
      <div ref={ref} className="jr-thumb-in"><img src={a.img} alt="" draggable={false} style={{ objectPosition: a.pos }} /></div>
      <span>{a.role}</span>
    </div>
  );
}
function EventCanvas({ j, L, onOpen, status, drawSpokes }: {
  j: Journey; L: JLayout; onOpen: (p: PieceId) => void; status: string | null; drawSpokes: boolean;
}) {
  const d = j.draft;
  const mode = L.mode;
  const filledIds = PIECE_ORDER.filter((p) => filled(d, p));
  const next = PIECE_ORDER.find((p) => !filled(d, p)) ?? null;
  const fmt = formatById(d.format);
  const venue = venueById(d.venue);
  const strip = mode === "strip";
  // strip positions for mobile chips
  const stripPos: Record<string, number> = {};
  let sx = 12;
  for (const p of PIECE_ORDER) {
    {
      stripPos[p] = sx;
      sx += SLOT[p].w * STRIP_K + (p === "artist" ? Math.max(0, d.artists.length - 1) * 30 : 0) + 10;
    }
  }
  const ringPts = filledIds.map((p) => ({ x: SLOT[p].x, y: SLOT[p].y }));
  const ring = smoothPath(ringPts, filledIds.length === PIECE_ORDER.length);
  const last = filledIds[filledIds.length - 1];
  const toNext = next && last ? `M${SLOT[last].x} ${SLOT[last].y} Q${f2((SLOT[last].x + SLOT[next].x) / 2 + (CORE.x - (SLOT[last].x + SLOT[next].x) / 2) * 0.35)} ${f2((SLOT[last].y + SLOT[next].y) / 2 + (CORE.y - (SLOT[last].y + SLOT[next].y) / 2) * 0.35)} ${SLOT[next].x} ${SLOT[next].y}` : null;
  const coreToNext = next && !last ? (() => { const sp = spoke(next); return `M${f2(sp.x2)} ${f2(sp.y2)} L${f2(sp.x1)} ${f2(sp.y1)}`; })() : null;
  const st: CSSProperties = strip
    ? { transform: `translate(0px, ${L.navH}px)`, width: L.vw }
    : { transform: `translate(${f2(L.frame.x)}px, ${f2(L.frame.y)}px) scale(${L.frame.s.toFixed(4)})` };
  const interactive = mode === "side" || mode === "corner" || mode === "strip";
  return (
    <div className={`jr-canvas is-${mode}`} style={st} aria-label="Событие" role="region">
      <div className="jr-canvas-in" style={strip ? { width: sx + 12 } : undefined}>
        {!strip && (
          <svg className="jr-thread" width={CW} height={CH} viewBox={`0 0 ${CW} ${CH}`} aria-hidden>
            <ellipse className="jr-orn" cx={CORE.x} cy={CORE.y} rx={CORE.w * 0.86} ry={CORE.h * 0.78} transform={`rotate(-5 ${CORE.x} ${CORE.y})`} />
            {PIECE_ORDER.map((p) => {
              const sp = spoke(p);
              const on = filled(d, p);
              return (
                <g key={p + (on ? `-on-${j.rev[p]}` : "-off")} className={on ? "on" : "off"}>
                  <path className="jr-spoke" d={`M${f2(sp.x1)} ${f2(sp.y1)} L${f2(sp.x2)} ${f2(sp.y2)}`} pathLength={1} />
                  {on && drawSpokes && <circle className="jr-node" cx={sp.x2} cy={sp.y2} r={2.6} />}
                </g>
              );
            })}
            {ring && <path key={`ring-${filledIds.join("")}`} className="jr-ring" d={ring} pathLength={1} />}
            {toNext && <path key={`next-${next}-${last}`} className="jr-next" d={toNext} />}
            {coreToNext && <path key={`cn-${next}`} className="jr-next" d={coreToNext} />}
            {filledIds.map((p) => <circle key={p} className="jr-node" cx={SLOT[p].x} cy={SLOT[p].y} r={0} />)}
            {d.artists.slice(1).map((a, k) => {
              const s = SLOT.artist;
              const x = s.x - s.w / 2 + 6 + k * 58 + 22, y = s.y + s.h / 2 + 14;
              return <path key={a} className="jr-branch" d={`M${s.x - 30} ${s.y + s.h / 2} Q${s.x - 30} ${y + 4} ${x} ${y}`} pathLength={1} />;
            })}
          </svg>
        )}
        {!strip && (
          <div className="jr-core" style={{ left: CORE.x - CORE.w / 2, top: CORE.y - CORE.h / 2, width: CORE.w, height: CORE.h }}>
            {venue && <img key={venue.id} className="jr-core-img" src={venue.img} alt="" draggable={false} />}
            <div className="jr-core-txt">
              <span className="jp-k">Событие</span>
              <b>{fmt ? fmt.title : "Новое событие"}</b>
              <span className="jr-core-n"><Roll value={String(filledIds.length)} /> / 7</span>
            </div>
            <div className="jr-core-dots">{PIECE_ORDER.map((p) => <i key={p} className={filled(d, p) ? "on" : ""} />)}</div>
            <span className="jr-core-check">08 · Проверка</span>
          </div>
        )}
        {PIECE_ORDER.map((p, k) => {
          if (filled(d, p)) return null;
          const s = SLOT[p];
          const tf = strip ? `translate(${f2(stripPos[p] ?? 0)}px, 12px) scale(${STRIP_K})` : `translate(${f2(s.x - s.w / 2)}px, ${f2(s.y - s.h / 2)}px)`;
          return (
            <button key={p} type="button" className={`jr-slot${p === next ? " is-next" : ""}`} style={{ width: s.w, height: s.h, transform: tf }}
              aria-label={`Открыть раздел «${PIECE_LABEL[p]}»`} onClick={() => onOpen(p)} disabled={!interactive}>
              <span>{String(k + 1).padStart(2, "0")}</span><b>{PIECE_LABEL[p]}</b>
            </button>
          );
        })}
        {PIECE_ORDER.map((p) => filled(d, p) && (
          <Piece key={p} id={p} d={d} rev={j.rev[p]} mode={mode} stripX={stripPos[p] ?? 0}
            onOpen={() => onOpen(p)} status={p === "artist" ? status : null} interactive={interactive} />
        ))}
        {d.artists.slice(1).map((a, k) => <ArtistThumb key={a} id={a} k={k} mode={mode} stripX={stripPos.artist ?? 0} />)}
      </div>
    </div>
  );
}
interface SP { j: Journey; go: (a: JAction) => void; L: JLayout }
function StageHead({ k, lines, sub, delay = 0 }: { k: string; lines: string[]; sub?: string; delay?: number }) {
  return (
    <header className="jr-head">
      <span className="jr-eyebrow">{k}</span>
      <MaskText lines={lines} className="jr-h" delay={delay} />
      {sub && <p className="jr-sub" style={{ animationDelay: `${delay + 160}ms` }}>{sub}</p>}
    </header>
  );
}
function EventOverviewStage({ j, go }: SP) {
  const complete = PIECE_ORDER.filter(p => filled(j.draft, p)).length;
  return <div className="jr-stage jr-event-overview">
    <StageHead k="ВАШЕ СОБЫТИЕ" lines={["Начните с любого раздела."]} sub="Бюджет, гости, площадка или артист — заполняйте в удобном порядке. Пазл тоже работает как меню." />
    <div className="jr-overview-grid">{PIECE_ORDER.map(p => <button key={p} type="button" onClick={() => go({ type: "scene", scene: SCENE_OF[p] })}>
      <span>{filled(j.draft, p) ? "✓ СОХРАНЕНО" : "МОЖНО ЗАПОЛНИТЬ"}</span><strong>{PIECE_LABEL[p]}</strong>
      <em>{filled(j.draft, p) ? rowValue(p, j.draft) : "Открыть раздел"}</em></button>)}</div>
    <p className="jr-fine">Сохранено {complete} из 7 разделов. Изменить уже заполненный раздел можно в любое время.</p>
    <div className="jr-actions"><button type="button" className="jr-btn" disabled={complete !== 7} onClick={() => go({ type: "scene", scene: "review" })}>Проверить событие</button></div>
  </div>;
}
function FormatStage({ j, go }: SP) {
  const bus = useContext(FlightCtx);
  const [sel, setSel] = useState<string | null>(null);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const pick = (id: string) => {
    if (sel) return;
    setSel(id);
    {
      const b = boxOf(refs.current[id]?.querySelector(".jr-fmt-img"));
      if (b) bus.put("piece-format", { from: b, r: 10, arc: 50, dur: 1000 });
      const patch = { format: id };
      go({ type: "set", piece: "format", patch, next: nextScene({ ...j.draft, ...patch }) });
    }
  };
  return (
    <div className={`jr-stage jr-format${sel ? " has-sel" : ""}`}>
      <StageHead k="01 · Формат" lines={["Что планируем?"]} />
      <div className="jr-fmt-grid">
        {FORMATS.map((f, k) => (
          <button key={f.id} ref={(el) => { refs.current[f.id] = el; }} type="button"
            className={`jr-fmt${sel === f.id ? " is-sel" : ""}${j.draft.format === f.id && !sel ? " is-cur" : ""}${sel && sel !== f.id ? " is-away" : ""}`}
            style={{ "--i": k, "--ax": `${(k % 3 - 1) * 14}px`, "--ay": `${(Math.floor(k / 3) ? 1 : -1) * 10}px` } as CSSProperties}
            onClick={() => pick(f.id)}>
            <span className="jr-fmt-img"><img src={f.img} alt="" draggable={false} /></span>
            <span className="jr-fmt-t"><i className="jr-marker" /><b>{f.title}</b><em>{f.note}</em></span>
          </button>
        ))}
      </div>
    </div>
  );
}
function DateStage({ j, go }: SP) {
  const [date, setDate] = useState(j.draft.dateISO ?? "");
  const [time, setTime] = useState(j.draft.time ?? "");
  const [city, setCity] = useState(j.draft.city ?? j.identity.city ?? "Москва");
  const save = () => {
    if (!date || !time || !city.trim() || date < localDateISO()) return;
    const patch = { date: Number(date.slice(-2)), dateISO: date, time, city: city.trim() };
    go({ type: "set", piece: "date", patch, next: nextScene({ ...j.draft, ...patch }) });
  };
  return <div className="jr-stage jr-date jr-date-flex">
    <StageHead k="02 · Дата и город" lines={["Когда и где?"]} />
    <div className="jr-event-date-controls">
      <DateTimeField label="Дата события" kind="date" value={date} min={localDateISO()} onChange={setDate} />
      <DateTimeField label="Начало события" kind="time" value={time} onChange={setTime} />
      <DateTimeField label="Окончание события" kind="time" value={j.draft.endsAt || "23:30"} onChange={endsAt => go({type:"set",piece:"date",patch:{endsAt}})} />
      <label className="jr-event-city">Город<input value={city} maxLength={120} onChange={e => setCity(e.target.value)} /></label>
    </div>
    <div className="jr-chips" role="radiogroup" aria-label="Город">
      {CITIES.slice(0, 4).map(c => <button key={c} type="button" role="radio" aria-checked={c === city} className={c === city ? "on" : ""} onClick={() => setCity(c)}>{c}</button>)}
    </div>
    <p className="jr-fine">Доступность исполнителей и площадки подтвердят в ответе на заявку.</p>
    <div className="jr-actions"><button type="button" className="jr-btn" disabled={!date || !time || !city.trim()} onClick={save}>Сохранить дату и время</button></div>
  </div>;
}
const GUEST_PRESETS: { v: number; label: string }[] = [
  { v: 30, label: "до 30" }, { v: 50, label: "50" }, { v: 100, label: "100" }, { v: 150, label: "150" }, { v: 200, label: "200+" },
];
function GuestsStage({ j, go }: SP) {
  const bus = useContext(FlightCtx);
  const [n, setN] = useState(j.draft.guests ?? 150);
  const [sending, setSending] = useState(false);
  const block = useRef<HTMLDivElement>(null);
  const confirm = () => {
    if (sending) return;
    setSending(true);
    {
      const b = boxOf(block.current);
      if (b) bus.put("piece-guests", { from: b, arc: 30, dur: 950 });
      const patch = { guests: n };
      go({ type: "set", piece: "guests", patch, next: nextScene({ ...j.draft, ...patch }) });
    }
  };
  const clamp = (v: number) => Math.max(10, Math.min(200, v));
  return (
    <div className={`jr-stage jr-guests${sending ? " is-sending" : ""}`}>
      <StageHead k="03 · Гости" lines={["Сколько будет", "гостей?"]} />
      <div className="jr-guests-body">
        <div ref={block} className="jr-guests-block">
          <div className="jr-guests-n" aria-live="polite"><Roll value={n >= 200 ? "200+" : String(n)} /></div>
          <span className="jr-guests-about">примерно</span>
          <div className="jr-guests-av" aria-hidden>{AVATARS.map((a, k) => <img key={a} src={a} alt="" style={{ "--i": k } as CSSProperties} />)}</div>
        </div>
        <div className="jr-guests-ctl">
          <button type="button" className="jr-round" onClick={() => setN((v) => clamp(v - 10))} aria-label="Меньше">−</button>
          <button type="button" className="jr-round" onClick={() => setN((v) => clamp(v + 10))} aria-label="Больше">+</button>
        </div>
        <div className="jr-chips" role="radiogroup" aria-label="Количество гостей">
          {GUEST_PRESETS.map((p) => (
            <button key={p.v} type="button" role="radio" aria-checked={n === p.v} className={n === p.v ? "on" : ""} onClick={() => setN(p.v)}>{p.label}</button>
          ))}
        </div>
        <div className="jr-actions">
          <button type="button" className="jr-btn" onClick={confirm}>Продолжить</button>
        </div>
      </div>
    </div>
  );
}
function localDateISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
function RiderStage({ j, go }: SP) {
  const [requirements, setRequirements] = useState<string[]>(j.draft.rider?.requirements ?? []);
  const [notes, setNotes] = useState(j.draft.rider?.notes ?? "");
  const a = ARTISTS.find(x => x.id === j.draft.artists[0]);
  const v = venueById(j.draft.venue);
  const save = () => {
    const patch = { rider: { matches: 0, open: requirements.length, requirements: [...requirements], notes: notes.trim() } };
    go({ type: "set", piece: "rider", patch, next: nextScene({ ...j.draft, ...patch }) });
  };
  return <div className="jr-stage jr-rider jr-rider-flex">
    <StageHead k="06 · Райдер" lines={["Какие условия нужны?"]} sub="Заполните требования сейчас — артиста и площадку можно выбрать позже." />
    <div className="jr-rider-context"><span>Артист: <b>{a?.name ?? "ещё не выбран"}</b></span><span>Площадка: <b>{v?.name ?? "ещё не выбрана"}</b></span></div>
    <fieldset className="jr-rider-options"><legend>Отметьте нужные условия</legend>
      {RIDER.map(r => <label key={r.sec}><input type="checkbox" checked={requirements.includes(r.sec)} onChange={e => setRequirements(xs => e.target.checked ? [...xs, r.sec] : xs.filter(x => x !== r.sec))} />
        <span><strong>{r.sec}</strong><em>{r.need}</em></span></label>)}
    </fieldset>
    <label className="jr-rider-notes">Ваши требования и пожелания<textarea rows={4} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Например, время монтажа, условия доступа и оборудование" /></label>
    <p className="jr-fine">Совместимость и выполнение требований подтвердят участники. Выбор условий не означает подтверждения площадкой.</p>
    <div className="jr-actions"><button type="button" className="jr-btn" onClick={save}>Сохранить райдер</button></div>
  </div>;
}
const BUDGET_PRESETS = [200000, 250000, 300000, 400000];
function budgetLines(d:EventDraft) {const arts=d.artists.map(artistById); const artist=arts.reduce((s,a)=>s+a.price,0);const venue=venueById(d.venue)?.price??0;return {arts,artist,venue,total:artist+venue};}
function BudgetStage({ j, go }: SP) {
  const bus = useContext(FlightCtx);
  const { arts, artist, venue, total } = budgetLines(j.draft);
  const [limit, setLimit] = useState<number>(j.draft.budget ?? Math.max(250000, Math.ceil(total / 50000) * 50000));
  const [sending, setSending] = useState(false);
  const fold = useRef<HTMLDivElement>(null);
  const save = () => {
    if (sending) return;
    setSending(true);
    {
      const b = boxOf(fold.current);
      if (b) bus.put("piece-budget", { from: b, r: 12, arc: -30, dur: 950 });
      go({ type: "set", piece: "budget", patch: { budget: limit }, next: nextScene({ ...j.draft, budget: limit }) });
    }
  };
  const v = venueById(j.draft.venue);
  return (
    <div className={`jr-stage jr-budget${sending ? " is-sending" : ""}`}>
      <StageHead k="07 · Бюджет" lines={["Бюджет события"]} />
      <div className="jr-budget-lines">
        <div className="jr-bl" style={{ "--i": 0 } as CSSProperties}><span>{arts.length ? `Артист${arts.length > 1 ? `ы · ${arts.length}` : ` · ${arts[0].name}`}` : "Артист ещё не выбран"}</span><b>{artist ? rub(artist) : "По запросу"}</b></div>
        <div className="jr-bl" style={{ "--i": 1 } as CSSProperties}><span>{v ? `Площадка · ${v.name}` : "Площадка ещё не выбрана"}</span><b>{venue ? rub(venue) : "По запросу"}</b></div>
        <div className="jr-bl is-muted" style={{ "--i": 2 } as CSSProperties}><span>Дополнительно</span><b>—</b></div>
        <div className="jr-bl is-total" style={{ "--i": 3 } as CSSProperties}><span>Тарифы из каталога<small>По выбранным участникам</small></span><b>{total ? rub(total) : "—"}</b></div>
      </div>
      <div ref={fold} className="jr-budget-limit">
        <span className="jr-field-l">Ваш бюджет</span>
        <div className="jr-budget-val">до <Roll value={rub(limit)} /></div>
        <label className="jr-own-budget">Указать свой бюджет<input type="number" min="1" step="1" value={limit || ""} inputMode="numeric" onChange={e => setLimit(Math.max(0, Math.floor(Number(e.target.value))))} /></label>
        <div className="jr-chips" role="radiogroup" aria-label="Бюджет">
          {BUDGET_PRESETS.map((p) => <button key={p} type="button" role="radio" aria-checked={limit === p} className={limit === p ? "on" : ""} onClick={() => setLimit(p)}>до {rub(p)}</button>)}
        </div>
        {limit < total && <p className="jr-note">Ориентир выше бюджета — участники увидят это в заявке.</p>}
      </div>
      <p className="jr-fine">Ваш бюджет — пожелание заказчика. Тарифы берутся из API. Если тариф не указан, стоимость уточняется. Итоговые стоимость и условия подтвердят участники.</p>
      <div className="jr-actions">
        <button type="button" className="jr-btn" disabled={!Number.isSafeInteger(limit) || limit < 1} onClick={save}>Сохранить бюджет</button>
      </div>
    </div>
  );
}
function rowValue(id: PieceId, d: EventDraft) {
  switch (id) {
    case "format": return formatById(d.format)?.title ?? "—";
    case "date": return d.dateISO ? `${eventDateText(d)} · ${d.city}` : "—";
    case "guests": return d.guests ? `${d.guests >= 200 ? "200+" : d.guests} ${plural(d.guests, "гость", "гостя", "гостей")}` : "—";
    case "artist": return d.artists.map((a) => artistById(a).name).join(", ") || (d.artistsDeferred ? "Подберём позже" : "—");
    case "venue": { const v = venueById(d.venue); return v ? v.name : d.venueDeferred ? "Подберём позже" : "—"; }
    case "rider": return d.rider ? d.rider.requirements?.join(", ") || d.rider.notes || "Требования сохранены" : "—";
    case "budget": return d.budget ? `до ${rub(d.budget)}` : "—";
  }
}
function ReviewStage({ j, go, L, onSent }: SP & { onSent: () => void }) {
  const later = useTimers();
  const root = useRef<HTMLDivElement>(null);
  const [landed, setLanded] = useState<Set<string>>(() => new Set());
  const [ready, setReady] = useState(false);
  const [edit, setEdit] = useState<{ id: PieceId; from: Box } | null>(null);
  const [sending, setSending] = useState<0 | 1 | 2 | 3>(0);
  const [sendPath, setSendPath] = useState<string | null>(null);
  const d = j.draft;
  const v = venueById(d.venue);
  const a = artistById(d.artists[0]);
  const { total } = budgetLines(d);

  useLayoutEffect(() => {
    const reduce = prefersReduced();
    const canvas = document.querySelector<HTMLElement>(".jr-canvas");
    const pieces = PIECE_ORDER.map((p) => document.querySelector<HTMLElement>(`.jr-piece-${p} .jr-piece-in`));
    if (L.mobile || reduce || !canvas || pieces.some((p) => !p)) {
      PIECE_ORDER.forEach((p, k) => later(() => setLanded((s) => new Set(s).add(p)), 80 + k * 70));
      later(() => setReady(true), 700);
      return;
    }
    // 1 · pieces move inward one by one, a node lights at each landing, the thread contracts
    canvas.classList.add("is-assemble");
    pieces.forEach((el, k) => {
      const s = SLOT[PIECE_ORDER[k]];
      const dx = (CORE.x - s.x) * 0.16, dy = (CORE.y - s.y) * 0.16;
      el!.style.transition = `translate 520ms ${MOTION.settle} ${k * 80}ms`;
      el!.style.translate = `${f2(dx)}px ${f2(dy)}px`;
    });
    // 2 · after a 300ms hold, every piece travels into its place in the summary
    const T = 7 * 80 + 520 + 300;
    later(() => {
      pieces.forEach((el, k) => {
        const p = PIECE_ORDER[k];
        const target = boxOf(root.current?.querySelector(`[data-slot="${p}"]`));
        if (!target) { setLanded((s) => new Set(s).add(p)); return; }
        flyTo(el!, target, { rFrom: 12, rTo: p === "venue" || p === "artist" ? 16 : 6, dur: 780, delay: k * 80, ease: MOTION.sym, arc: (k % 2 ? 1 : -1) * 30, fadeOut: true,
          onDone: () => setLanded((s) => new Set(s).add(p)) });
      });
      later(() => canvas.classList.add("is-gone"), 300);
    }, T);
    later(() => setReady(true), T + 7 * 80 + 700);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEdit = (id:PieceId, _el:HTMLElement) => go({type:'scene',scene:SCENE_OF[id]});
  const send = () => live.onContinue();
  const row = (id: PieceId, label: string) => (
    <button type="button" key={id} data-slot={id}
      className={`jr-rev-row${landed.has(id) ? " is-landed" : ""}${edit?.id === id ? " is-detached" : ""}`}
      onClick={(e) => openEdit(id, e.currentTarget)} aria-label={`${label}: ${rowValue(id, d)} — изменить`}>
      <span className="jr-rev-k">{label}</span>
      <b>{id === "guests" || id === "budget" ? <Roll value={rowValue(id, d)} /> : rowValue(id, d)}</b>
      <span className="jr-rev-edit">изменить</span>
    </button>
  );
  return (
    <div ref={root} className={`jr-stage jr-rev${ready ? " is-ready" : ""}${L.mobile ? " is-mobile" : ""} send-${sending}`}>
      <div className="jr-rev-comp">
        <div className={`jr-rev-hero${landed.has("venue") ? " is-landed" : ""}`} data-slot="venue" data-sid={`venue-${v?.id}`}>
          <img src={v?.img || formatById(d.format)?.img || placeholder} alt={v?.name || "Формат события"} draggable={false} />
          <span className="jr-rev-cap">{v ? v.name : "Площадка — подберём позже"}</span>
        </div>
        <div className={`jr-rev-portrait${landed.has("artist") ? " is-landed" : ""}`} data-slot="artist" data-sid={`artist-${a.id}`}>
          <img src={a.img} alt={a.name} draggable={false} style={{ objectPosition: a.pos }} />
          <span className="jr-rev-cap">{d.artists.length ? `${a.name} · ${a.role}` : "Артист — подберём позже"}</span>
        </div>
        {d.artists.slice(1).map((x, k) => (
          <div key={x} className={`jr-rev-extra${landed.has("artist") ? " is-landed" : ""}`} style={{ "--i": k } as CSSProperties}>
            <img src={artistById(x).img} alt={artistById(x).name} style={{ objectPosition: artistById(x).pos }} />
          </div>
        ))}
        <svg className="jr-rev-outline" aria-hidden preserveAspectRatio="none" viewBox="0 0 100 100"><rect x="0.5" y="0.5" width="99" height="99" rx="2" pathLength={1} vectorEffect="non-scaling-stroke" /></svg>
      </div>
      <div className="jr-rev-side">
        <header className="jr-head">
          <span className="jr-eyebrow">08 · Проверка</span>
          {ready && <MaskText lines={["Событие собрано."]} className="jr-h" />}
          {ready && <p className="jr-sub">Проверьте детали перед отправкой заявки.</p>}
        </header>
        <label className="v5-title">Название события<input maxLength={200} value={live.draft.title} onChange={e=>live.onDraftChange({...live.draft,title:e.target.value})} /></label><div className="jr-rev-rows">
          {row("format", "Формат")}
          {row("date", "Когда и где")}
          {row("guests", "Гости")}
          {row("artist", d.artists.length > 1 ? "Артисты" : "Артист")}
          {row("venue", "Площадка")}
          {row("rider", "Райдер")}
          {row("budget", "Бюджет")}
          <div className="jr-rev-est"><span>Предварительный ориентир</span><b>{total ? `от ${rub(total)}` : "По запросу"}</b></div>
        </div>
        <div className="jr-actions">
          <button type="button" className={`jr-btn${sending ? " is-busy" : ""}`} onClick={send} disabled={!ready || live.submitting}>
            <span key={sending ? "s" : "n"} className="jr-btn-l">{live.submitting ? "Отправляем…" : "Отправить заявку"}</span>
          </button>
          <button type="button" className="jr-link-btn" disabled={!ready || !!sending}
            onClick={() => { const el = root.current?.querySelector<HTMLElement>('[data-slot="format"]'); if (el) openEdit("format", el); }}>Изменить</button>
        </div>
      </div>
      {sendPath && (
        <svg className="jr-send" width={L.vw} height={L.vh} aria-hidden>
          <path d={sendPath} className="base" />
          <path d={sendPath} className="run" pathLength={1} />
        </svg>
      )}

    </div>
  );
}
function LiveCatalog({j,go,L,kind}:{j:Journey;go:(a:JAction)=>void;L:JLayout;kind:'artist'|'venue'}){
 const bus=useContext(FlightCtx); const [query,setQuery]=useState('');
 const items=kind==='artist'?live.talents.map(t=>({id:t.id,name:t.name,detail:t.roleLabel,price:t.honorariumFrom,img:t.mediaUrl})):live.venues.map(v=>({id:v.id,name:v.name,detail:v.city,price:v.honorariumFrom,img:v.mediaUrl}));
 const selected=(id:string)=>kind==='artist'?j.draft.artists.includes(id):j.draft.venue===id;
 const choose=(id:string,el:HTMLElement)=>{
  const b=boxOf(el);if(b)bus.put(`piece-${kind}`,{from:b,r:14,arc:40,dur:950});
  const patch:Partial<EventDraft>=kind==='artist'?{artists:selected(id)?j.draft.artists.filter(x=>x!==id):[...j.draft.artists,id],artistsDeferred:false}:{venue:selected(id)?null:id,venueDeferred:false};
  go({type:'set',piece:kind,patch,next:'eventOverview'});
 };
 return <div className="jr-stage v5-catalog"><StageHead k={kind==='artist'?'04 · Артисты':'05 · Площадка'} lines={[kind==='artist'?'Кто создаст атмосферу?':'Найдём ваше место.']} sub="Доступность и условия участник подтвердит в ответе на заявку."/>
  <label className="jr-search"><input aria-label={kind==='artist'?'Поиск артистов':'Поиск площадок'} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Поиск по имени или названию"/></label>
  {live.loadingTalents?<p role="status">Загружаем каталог…</p>:live.talentsError?<div role="alert"><p>Каталог временно недоступен. Черновик сохранён.</p><button className="jr-link-btn" onClick={live.onReloadCatalog}>Повторить загрузку</button></div>:<div className="v5-catalog-grid">{items.filter(x=>x.name.toLowerCase().includes(query.toLowerCase())).map((item,i)=><article className="v5-supplier" key={item.id} style={{'--i':i} as CSSProperties}>
   <img src={item.img||placeholder} alt=""/><h3>{item.name}</h3><p>{item.detail}</p><p>{item.price!=null?`от ${rub(item.price)}`:'Стоимость по запросу'}</p>
   <button className="jr-btn" disabled={kind==='artist'&&!selected(item.id)&&j.draft.artists.length>=3} onClick={e=>choose(item.id,e.currentTarget.closest('article')!)}>{selected(item.id)?'Убрать из события':'Добавить в событие'}</button>
   <a className="jr-link-btn" href={`/${kind==='artist'?'artists':'venues'}/${encodeURIComponent(item.id)}`}>Открыть профиль</a>
  </article>)}{!items.length&&<p>В этом городе пока нет опубликованных вариантов. Можно продолжить сборку и подобрать участника позже.</p>}</div>}
  <div className="jr-actions"><button className="jr-link-btn" onClick={()=>go({type:'set',piece:kind,patch:kind==='artist'?{artistsDeferred:true}:{venueDeferred:true},next:'eventOverview'})}>Подобрать позже</button></div>
 </div>;
}
return function LiveScene(props:EventStudioMapProps){
 live=props;
 const visual=toVisual(props.draft);
 ARTISTS.splice(0,ARTISTS.length,...props.talents.map(t=>({id:t.id,name:t.name,role:t.roleLabel,genre:'',cat:'music' as ArtistCat,price:t.honorariumFrom??0,free:false,img:t.mediaUrl||placeholder,city:props.draft.city,rating:''})));
 VENUES.splice(0,VENUES.length,...props.venues.map(v=>({id:v.id,name:v.name,area:v.district||v.city,cap:0,minCap:0,price:v.honorariumFrom??0,free:false,img:v.mediaUrl||placeholder,kind:'Площадка'})));
 const validScenes=new Set<JScene>(['eventOverview','eventFormat','eventDate','eventGuests','artistDiscovery','venueDiscovery','rider','budget','review']);
 const [scene,setScene]=useState<JScene>('eventOverview');
 const [rev,setRev]=useState(INIT_JOURNEY.rev);
 const bus=useFlightBus(); const {vw,vh}=useViewport(); const mobile=isMobile(vw,vh);
 const mode:CanvasMode=scene==='review'?'review':mobile?'strip':'side';
 const L=computeLayout(vw,vh,mode);
 const j:Journey={...INIT_JOURNEY,scene,draft:visual,rev,path:'event'};
 const navigate=(next:JScene,push=true)=>{setScene(next);if(push)window.history.pushState(null,'',`#${next}`);};
 useEffect(()=>{const sync=()=>{const s=window.location.hash.slice(1) as JScene;setScene(validScenes.has(s)?s:'eventOverview')};sync();window.addEventListener('popstate',sync);return()=>window.removeEventListener('popstate',sync);},[]);
 useEffect(()=>{const title=document.querySelector<HTMLElement>('.jr-root .is-entering .jr-h');if(title){title.tabIndex=-1;title.focus({preventScroll:true})}},[scene]);
 const go=(action:JAction)=>{
  if(action.type==='scene'&&validScenes.has(action.scene))navigate(action.scene);
  if(action.type==='set'){
   props.onDraftChange(fromVisual(props.draft,{...visual,...action.patch}));
   setRev(old=>({...old,[action.piece]:old[action.piece]+1}));
   if(action.next)navigate(action.next);
  }
 };
 const sp={j,go,L};let stage:ReactNode=null;
 switch(scene){
  case 'eventOverview':stage=<EventOverviewStage {...sp}/>;break;
  case 'eventFormat':stage=<FormatStage {...sp}/>;break;
  case 'eventDate':stage=<DateStage {...sp}/>;break;
  case 'eventGuests':stage=<GuestsStage {...sp}/>;break;
  case 'artistDiscovery':stage=<LiveCatalog {...sp} kind="artist"/>;break;
  case 'venueDiscovery':stage=<LiveCatalog {...sp} kind="venue"/>;break;
  case 'rider':stage=<RiderStage {...sp}/>;break;
  case 'budget':stage=<BudgetStage {...sp}/>;break;
  case 'review':stage=<ReviewStage {...sp} onSent={()=>{}}/>;break;
 }
 const saveLabel=props.saveStatus==='saving'?'Сохраняем…':props.saveStatus==='error'?'Не удалось сохранить':props.saveStatus==='offline'?'Офлайн · на этом устройстве':props.saveStatus==='conflict'?'Черновик обновлён в другой вкладке':'Черновик на устройстве';
 return <FlightCtx.Provider value={bus}><div data-booker-flexible-event="v5-integrated" className={`jr-root v5-live is-${mode}${mobile?' is-mobile':''}`}>
  <nav className="v5-nav"><a href="/" aria-label="Букер — главная">BUKER</a><button onClick={()=>navigate('eventOverview')}>Моё событие</button><span role="status">{saveLabel}</span>{props.saveStatus==='error'&&<button onClick={props.onRetrySave}>Повторить</button>}</nav>
  <EventCanvas j={j} L={L} onOpen={p=>navigate(SCENE_OF[p])} status={null} drawSpokes/>
  <Swap k={scene} rect={L.stage} className={`jr-stage-wrap is-${scene}`}>{stage}</Swap>
  {scene!=='eventOverview'&&<button className="v5-back jr-link-btn" onClick={()=>navigate('eventOverview')}>← К сборке события</button>}
  {props.submitError&&<div className="v5-alert" role="alert">{props.submitError}</div>}
 </div></FlightCtx.Provider>;
};

}
export default function FlexibleEventV5(props:EventStudioMapProps){const Scene=useMemo(createScene,[]);return <Scene {...props}/>;}
