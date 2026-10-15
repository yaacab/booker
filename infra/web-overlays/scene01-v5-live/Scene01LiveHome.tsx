"use client";

import { installSceneRecovery } from "@/lib/scene01Recovery";

import {
  useCallback, useEffect, useMemo, useRef, useState,
  type CSSProperties, type ReactNode,
} from "react";

/* ================================================================
   BUKER — SCENE 01 · INTRO / PUZZLE ASSEMBLY
   Fragments → attraction → assembly → seams dissolve → brand →
   interaction → transition into registration.
   ================================================================ */

/* ---------- assets ---------- */
const un = (id: string, w: number) =>
  `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=72`;
const PHOTO = {
  performer: un("1493225457124-a3eb161ffa5f", 760),
  concert: un("1470229722913-7c0e2dbbafd3", 760),
  stage: un("1506157786151-b8491531f063", 760),
  venue: un("1517248135467-4c7edcad34c4", 760),
  dinner: un("1464366400600-7168b8af9bc3", 760),
  plated: un("1414235077428-338989a2e8c0", 760),
  toast: un("1470337458703-46ad1756a187", 640),
  crowd: un("1429962714451-bb934ecdc4ec", 640),
  hall: un("1519167758481-83f550bb49b3", 520),
  mic: un("1516280440614-37939bbacd81", 520),
};
const AVATARS = [
  "1500648767791-00dcc994a43e",
  "1494790108377-be9c29b29330",
  "1438761681033-6461ffad8d80",
  "1472099645785-5658abf4ff4e",
].map((id) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=96&h=96&q=70`);

/* ---------- layout ---------- */
type Kind =
  | "artist" | "concert" | "toast" | "eventtype" | "venue" | "centerA"
  | "centerB" | "dj" | "calendar" | "dinner" | "guests" | "crowd";
type Orientation = "land" | "port";

interface LayoutDef { W: number; H: number; colW: number[]; rowH: number[]; grid: Kind[][] }
const LAYOUTS: Record<Orientation, LayoutDef> = {
  land: {
    W: 1440, H: 810, colW: [360, 360, 360, 360], rowH: [270, 270, 270],
    grid: [
      ["artist", "concert", "toast", "eventtype"],
      ["venue", "centerA", "centerB", "dj"],
      ["calendar", "dinner", "guests", "crowd"],
    ],
  },
  port: {
    W: 760, H: 1300, colW: [220, 320, 220], rowH: [300, 350, 350, 300],
    grid: [
      ["artist", "concert", "eventtype"],
      ["venue", "centerA", "dj"],
      ["calendar", "centerB", "guests"],
      ["dinner", "toast", "crowd"],
    ],
  },
};

const DEPTH: Record<Kind, -1 | 0 | 1> = {
  centerA: -1, centerB: -1, concert: -1, dinner: -1, toast: -1,
  venue: 0, dj: 0, guests: 0,
  artist: 1, eventtype: 1, calendar: 1, crowd: 1,
};
const CARD_ROT: Partial<Record<Kind, number>> = {
  artist: -3, concert: 2, toast: -1.5, eventtype: 3, venue: -2.5, dj: 2.5,
  calendar: -2, dinner: 2.5, guests: -1.5, crowd: 2,
};
const CARD_PARALLAX: Partial<Record<Kind, number>> = {
  artist: 1.4, concert: 0.7, toast: 0.8, eventtype: 1.3, venue: 1.0, dj: 1.1,
  calendar: 1.4, dinner: 0.8, guests: 1.0, crowd: 1.3,
};
const ROLE_OF: Partial<Record<Kind, number>> = { eventtype: 0, artist: 1, venue: 2 };
const ROLES = [
  { kicker: "Я организую", title: "Заказчик", text: "Соберите событие целиком: артисты, площадка, дата и гости — в одном месте.", photo: PHOTO.plated },
  { kicker: "Я выступаю", title: "Исполнитель", text: "Музыканты, DJ, ведущие и шоу. Получайте запросы на выступления напрямую.", photo: PHOTO.performer },
  { kicker: "Я принимаю гостей", title: "Площадка", text: "Рестораны, лофты и террасы. Покажите пространство и свободные даты.", photo: PHOTO.venue },
];
const SATS = [
  { x: -0.015, y: 0.16, s: 0.17, img: PHOTO.hall, b: 7, d: 1.4, r: -14 },
  { x: 1.01, y: 0.25, s: 0.15, img: PHOTO.mic, b: 6, d: 1.2, r: 12 },
  { x: 0.02, y: 0.84, s: 0.19, img: PHOTO.stage, b: 8, d: 1.6, r: 9 },
  { x: 0.985, y: 0.78, s: 0.16, img: PHOTO.toast, b: 6, d: 1.3, r: -10 },
  { x: 0.72, y: 1.02, s: 0.14, img: PHOTO.crowd, b: 9, d: 1.8, r: 16 },
  { x: 0.22, y: -0.03, s: 0.12, img: PHOTO.dinner, b: 7, d: 1.5, r: -8 },
];

/* ---------- math ---------- */
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
const f2 = (n: number) => (Math.round(n * 100) / 100).toString();
function rng(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function bezier(x1: number, y1: number, x2: number, y2: number) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let lo = 0, hi = 1, t = x;
    for (let i = 0; i < 22; i++) {
      const v = sx(t);
      if (Math.abs(v - x) < 1e-5) break;
      if (v < x) lo = t; else hi = t;
      t = (lo + hi) / 2;
    }
    return sy(t);
  };
}
const E_ATTRACT = bezier(0.6, 0.02, 0.18, 1); // soft acceleration, long deceleration, no overshoot
const E_IO = bezier(0.65, 0, 0.35, 1);
const E_OUT = bezier(0.16, 1, 0.3, 1);
const E_CAM = bezier(0.55, 0, 0.2, 1);

/* ---------- puzzle geometry ---------- */
interface Side { kx: number; ky: number; c: number; t: number }
interface Cell {
  i: number; kind: Kind; col: number; row: number;
  x: number; y: number; w: number; h: number; cx: number; cy: number;
  sides: [Side, Side, Side, Side];
}
interface Seam { a: number; b: number; d: string }
interface Geo { W: number; H: number; pad: number; cells: Cell[]; seams: Seam[] }
const FLAT: Side = { kx: 0, ky: 0, c: 0.5, t: 0 };

function knobSegs(ax: number, ay: number, bx: number, by: number, s: Side, amp: number, ox: number, oy: number) {
  if ((!s.kx && !s.ky) || amp <= 0.001) return "";
  const L = Math.hypot(bx - ax, by - ay);
  const dx = (bx - ax) / L, dy = (by - ay) / L;
  const t = s.t, m = L * s.c, n = 0.45 * t, hw = 0.85 * t;
  const P = (u: number, v: number) =>
    `${f2(ax + dx * u + s.kx * v * amp + ox)} ${f2(ay + dy * u + s.ky * v * amp + oy)}`;
  return (
    `L${P(m - n, 0)}` +
    `C${P(m - n + 0.1 * t, 0.45 * t)} ${P(m - hw, 0.55 * t)} ${P(m - hw, 1.05 * t)}` +
    `C${P(m - hw, 1.55 * t)} ${P(m + hw, 1.55 * t)} ${P(m + hw, 1.05 * t)}` +
    `C${P(m + hw, 0.55 * t)} ${P(m + n - 0.1 * t, 0.45 * t)} ${P(m + n, 0)}`
  );
}
function piecePath(x0: number, y0: number, w: number, h: number, sides: Side[], amp: number, rad: number, ox: number, oy: number) {
  const R = Math.min(rad, w / 2, h / 2);
  const C = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]];
  let d = `M${f2(x0 + R + ox)} ${f2(y0 + oy)}`;
  for (let k = 0; k < 4; k++) {
    const [ax, ay] = C[k], [bx, by] = C[(k + 1) % 4], [cx, cy] = C[(k + 2) % 4];
    d += knobSegs(ax, ay, bx, by, sides[k], amp, ox, oy);
    const L = Math.hypot(bx - ax, by - ay), dx = (bx - ax) / L, dy = (by - ay) / L;
    d += `L${f2(bx - dx * R + ox)} ${f2(by - dy * R + oy)}`;
    if (R > 0.01) {
      const nL = Math.hypot(cx - bx, cy - by), nx = (cx - bx) / nL, ny = (cy - by) / nL;
      d += `Q${f2(bx + ox)} ${f2(by + oy)} ${f2(bx + nx * R + ox)} ${f2(by + ny * R + oy)}`;
    }
  }
  return d + "Z";
}

function buildGeo(def: LayoutDef): Geo {
  const r = rng(11);
  const X = [0], Y = [0];
  def.colW.forEach((w) => X.push(X[X.length - 1] + w));
  def.rowH.forEach((h) => Y.push(Y[Y.length - 1] + h));
  const rows = def.rowH.length, cols = def.colW.length;
  const mk = (len: number) => ({ dir: r() < 0.5 ? -1 : 1, c: 0.5 + (r() - 0.5) * 0.12, t: len * 0.16 });
  const vE = Array.from({ length: rows }, (_, ri) =>
    Array.from({ length: cols - 1 }, (_, ci) => mk(Math.min(def.rowH[ri], def.colW[ci], def.colW[ci + 1]))));
  const hE = Array.from({ length: rows - 1 }, (_, ri) =>
    Array.from({ length: cols }, (_, ci) => mk(Math.min(def.colW[ci], def.rowH[ri], def.rowH[ri + 1]))));
  const cells: Cell[] = [];
  for (let ri = 0; ri < rows; ri++)
    for (let ci = 0; ci < cols; ci++) {
      const top = ri > 0 ? { kx: 0, ky: hE[ri - 1][ci].dir, c: hE[ri - 1][ci].c, t: hE[ri - 1][ci].t } : FLAT;
      const right = ci < cols - 1 ? { kx: vE[ri][ci].dir, ky: 0, c: vE[ri][ci].c, t: vE[ri][ci].t } : FLAT;
      const bottom = ri < rows - 1 ? { kx: 0, ky: hE[ri][ci].dir, c: 1 - hE[ri][ci].c, t: hE[ri][ci].t } : FLAT;
      const left = ci > 0 ? { kx: vE[ri][ci - 1].dir, ky: 0, c: 1 - vE[ri][ci - 1].c, t: vE[ri][ci - 1].t } : FLAT;
      const w = def.colW[ci], h = def.rowH[ri];
      cells.push({
        i: cells.length, kind: def.grid[ri][ci], col: ci, row: ri,
        x: X[ci], y: Y[ri], w, h, cx: X[ci] + w / 2, cy: Y[ri] + h / 2,
        sides: [top, right, bottom, left],
      });
    }
  const seams: Seam[] = [];
  for (let ri = 0; ri < rows; ri++)
    for (let ci = 0; ci < cols - 1; ci++) {
      const e = vE[ri][ci], x = X[ci + 1];
      seams.push({ a: ri * cols + ci, b: ri * cols + ci + 1,
        d: `M${x} ${Y[ri]}` + knobSegs(x, Y[ri], x, Y[ri + 1], { kx: e.dir, ky: 0, c: e.c, t: e.t }, 1, 0, 0) + `L${x} ${Y[ri + 1]}` });
    }
  for (let ri = 0; ri < rows - 1; ri++)
    for (let ci = 0; ci < cols; ci++) {
      const e = hE[ri][ci], y = Y[ri + 1];
      seams.push({ a: ri * cols + ci, b: (ri + 1) * cols + ci,
        d: `M${X[ci]} ${y}` + knobSegs(X[ci], y, X[ci + 1], y, { kx: 0, ky: e.dir, c: e.c, t: e.t }, 1, 0, 0) + `L${X[ci + 1]} ${y}` });
    }
  return { W: def.W, H: def.H, pad: 84, cells, seams };
}

function satPath(seed: number) {
  const r = rng(seed);
  const s = (horizontal: boolean): Side => {
    const dir = r() < 0.5 ? -1 : 1;
    return r() < 0.15 ? FLAT : { kx: horizontal ? 0 : dir, ky: horizontal ? dir : 0, c: 0.5, t: 16 };
  };
  return piecePath(0, 0, 100, 100, [s(true), s(false), s(true), s(false)], 1, 0, 0, 0);
}

/* ---------- small icons ---------- */
const Heart = () => (
  <span className="bk-heart">
    <svg viewBox="0 0 24 24" width="13" height="13"><path d="M12 20s-7-4.4-9.2-8.6C1.3 8.3 3.2 5 6.4 5c2 0 3.2 1.1 3.9 2.2.3.5.9.5 1.2 0C12.2 6.1 13.5 5 15.5 5c3.2 0 5.1 3.3 3.6 6.4C19 15.6 12 20 12 20z" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
  </span>
);
const Ico = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width="13" height="13"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
const I_PEOPLE = "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.6-3.4 3.2-5.5 6.5-5.5s5.9 2.1 6.5 5.5M16 4.5a3.3 3.3 0 0 1 0 6.4M18 14.8c2 .7 3.2 2.5 3.5 5.2";
const I_RING = "M12 8l2-3h-4l2 3zM12 21a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z";
const I_GLASS = "M7 3h10l-1 7a4 4 0 0 1-8 0L7 3zM12 14v6M8.5 21h7";

/* ---------- board content (one continuous composition) ---------- */
function Photo({ src, pos }: { src: string; pos?: string }) {
  return <img className="bk-img" src={src} alt="" draggable={false} style={pos ? { objectPosition: pos } : undefined} />;
}
function Chip({ children }: { children: ReactNode }) {
  return <span className="bk-chip">{children}</span>;
}
function CardBody({ kind }: { kind: Kind }) {
  switch (kind) {
    case "artist":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.performer} pos="50% 30%" /><Heart />
        <div className="bk-label"><span className="bk-kicker">Исполнитель</span><span className="bk-title">Живая музыка<br />для ваших событий</span></div></div>);
    case "concert":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.concert} /><Chip>Концерты</Chip></div>);
    case "toast":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.toast} pos="50% 60%" /><Chip>Кейтеринг · бар</Chip></div>);
    case "dinner":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.dinner} /><Chip>Ужины и банкеты</Chip></div>);
    case "crowd":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.crowd} /><Chip>Атмосфера</Chip></div>);
    case "venue":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.venue} /><Heart />
        <div className="bk-label"><span className="bk-kicker">Площадка</span><span className="bk-title">Пространства<br />с характером</span></div></div>);
    case "dj":
      return (<div className="bk-card bk-photo"><Photo src={PHOTO.stage} pos="50% 40%" /><Heart />
        <div className="bk-label"><span className="bk-kicker">Артист</span><span className="bk-title">Maks Kay</span><span className="bk-sub">DJ · Melodic Techno</span></div></div>);
    case "eventtype":
      return (<div className="bk-card bk-paper bk-event">
        <span className="bk-kicker">Событие</span>
        <ul>
          <li><Ico d={I_PEOPLE} />Корпоратив</li>
          <li><Ico d={I_RING} />Свадьба</li>
          <li><Ico d={I_GLASS} />Частная вечеринка</li>
        </ul>
        <span className="bk-dark-pill">Создать событие</span>
      </div>);
    case "guests":
      return (<div className="bk-card bk-paper bk-guests">
        <span className="bk-kicker">Гости</span>
        <div className="bk-guests-n"><Ico d={I_PEOPLE} /><span>150</span></div>
        <div className="bk-avatars">{AVATARS.map((a) => <img key={a} src={a} alt="" draggable={false} />)}<span>+</span></div>
      </div>);
    case "calendar": {
      const days: { n: number; muted?: boolean }[] = [
        { n: 28, muted: true }, { n: 29, muted: true }, { n: 30, muted: true },
        ...Array.from({ length: 31 }, (_, k) => ({ n: k + 1 })), { n: 1, muted: true },
      ];
      return (<div className="bk-card bk-paper bk-cal">
        <span className="bk-kicker">Дата</span>
        <div className="bk-cal-head"><span>‹</span><b>Октябрь 2026</b><span>›</span></div>
        <div className="bk-cal-grid">
          {["пн", "вт", "ср", "чт", "пт", "сб", "вс"].map((d) => <i key={d}>{d}</i>)}
          {days.map((d, k) => <span key={k} className={d.muted ? "m" : d.n === 18 && !d.muted ? "on" : undefined}>{d.n}</span>)}
        </div>
      </div>);
    }
    default:
      return null;
  }
}

function BoardContent({ geo }: { geo: Geo }) {
  const { W, H } = geo;
  const centers = geo.cells.filter((c) => c.kind === "centerA" || c.kind === "centerB");
  const minX = Math.min(...centers.map((c) => c.x)), maxX = Math.max(...centers.map((c) => c.x + c.w));
  const minY = Math.min(...centers.map((c) => c.y)), maxY = Math.max(...centers.map((c) => c.y + c.h));
  const rx = (maxX - minX) / 2 - 16, ry = (maxY - minY) / 2 - 10;
  return (
    <div className="bk-board" style={{ width: W, height: H }}>
      <svg className="bk-orn" width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
        <ellipse cx={W / 2} cy={H / 2} rx={rx} ry={ry} transform={`rotate(-4 ${W / 2} ${H / 2})`} />
        <ellipse cx={W / 2 + 6} cy={H / 2 + 3} rx={rx * 0.93} ry={ry * 0.9} transform={`rotate(5 ${W / 2} ${H / 2})`} className="thin" />
        <circle cx={W / 2 - rx * 0.99} cy={H / 2 + ry * 0.14} r="2.4" />
        <circle cx={W / 2 + rx * 0.97} cy={H / 2 - ry * 0.18} r="2.4" />
      </svg>
      {geo.cells.map((c) => {
        if (c.kind === "centerA" || c.kind === "centerB") return null;
        const m = Math.min(c.w, c.h) * 0.085;
        const d = CARD_PARALLAX[c.kind] ?? 1;
        return (
          <div key={c.i} className={`bk-cell bk-${c.kind}`}
            style={{
              left: c.x + m, top: c.y + m, width: c.w - 2 * m, height: c.h - 2 * m,
              transform: `translate(calc(var(--mx, 0) * ${d * 5}px), calc(var(--my, 0) * ${d * 4}px)) rotate(${CARD_ROT[c.kind] ?? 0}deg)`,
            }}>
            <CardBody kind={c.kind} />
          </div>
        );
      })}
    </div>
  );
}

/* ---------- registration geometry ---------- */
interface Rect { cx: number; cy: number; w: number; h: number }
function regGeo(vw: number, vh: number) {
  const stacked = vw < 760 || vw / vh < 0.95;
  if (!stacked) {
    const top = Math.max(196, vh * 0.27);
    const gap = 28;
    const cw = Math.min(312, (vw - 120 - 2 * gap) / 3);
    const ch = Math.max(230, Math.min(cw * 1.34, vh - top - 116));
    const x0 = (vw - (3 * cw + 2 * gap)) / 2;
    const rects: Rect[] = [0, 1, 2].map((k) => ({ cx: x0 + cw / 2 + k * (cw + gap), cy: top + ch / 2, w: cw, h: ch }));
    return { rects, titleTop: top - 118, actionsTop: top + ch + 30, stacked };
  }
  const top = 172, gap = 12;
  const cw = Math.min(vw - 32, 480);
  const ch = Math.max(118, Math.min(178, (vh - top - 108 - 2 * gap) / 3));
  const rects: Rect[] = [0, 1, 2].map((k) => ({ cx: vw / 2, cy: top + ch / 2 + k * (ch + gap), w: cw, h: ch }));
  return { rects, titleTop: 76, actionsTop: top + 3 * ch + 2 * gap + 20, stacked };
}

/* ---------- scene ---------- */
type Phase = "intro" | "ready" | "transition" | "reg";
type StartAt = "intro" | "ready" | "reg";

interface ChooseInfo { role: number; card: DOMRect; photo: DOMRect; stacked: boolean }
function Scene({ orient, startAt, onPhase, onReplay, onChoose }: {
  orient: Orientation; startAt: StartAt; onPhase: (p: Phase) => void; onReplay: () => void;
  onChoose: (info: ChooseInfo) => void;
}) {
  const geo = useMemo(() => buildGeo(LAYOUTS[orient]), [orient]);
  const rootRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<Phase>("intro");
  const [selected, setSelected] = useState<number | null>(null);
  const [stacked, setStacked] = useState(false);
  const api = useRef<{ begin: () => void; hover: (k: number | null) => void; choose: (k: number) => void } | null>(null);
  const sats = useMemo(() => SATS.map((s, k) => ({ ...s, d: satPath(100 + k) })), []);

  useEffect(() => { onPhase(phase); }, [phase, onPhase]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const { W, H, pad, cells, seams } = geo;
    const q = <T extends Element>(sel: string) => root.querySelector(sel) as T;
    const qa = <T extends Element>(sel: string) => Array.from(root.querySelectorAll(sel)) as T[];
    const world = q<HTMLDivElement>(".bk-world");
    const pieceEls = qa<HTMLDivElement>(".bk-piece");
    const clipEls = pieceEls.map((p) => p.querySelector(".bk-piece-clip") as HTMLDivElement);
    const edgeEls = pieceEls.map((p) => p.querySelector(".bk-piece-edge") as SVGSVGElement);
    const edgePaths = pieceEls.map((p) => Array.from(p.querySelectorAll(".bk-piece-edge path")) as SVGPathElement[]);
    const roleLayers = pieceEls.map((p) => p.querySelector(".bk-role-layer") as HTMLDivElement | null);
    const roleInners = pieceEls.map((p) => p.querySelector(".bk-role-inner") as HTMLDivElement | null);
    const boardSpace = q<HTMLDivElement>(".bk-boardspace");
    const unified = q<HTMLDivElement>(".bk-unified");
    const glowCore = qa<SVGPathElement>(".bk-glow .core");
    const glowSoft = qa<SVGPathElement>(".bk-glow .soft");
    const linePaths = qa<SVGPathElement>(".bk-lines path");
    const lineNodes = qa<SVGCircleElement>(".bk-lines circle");
    const brand = q<HTMLDivElement>(".bk-brand");
    const word = q<HTMLSpanElement>(".bk-word");
    const tagLines = qa<HTMLSpanElement>(".bk-tag-line > span");
    const cta = q<HTMLDivElement>(".bk-cta-wrap");
    const satEls = qa<HTMLDivElement>(".bk-sat");
    const regHead = q<HTMLDivElement>(".bk-reg-head");
    const regActions = q<HTMLDivElement>(".bk-reg-actions");
    const foot = qa<HTMLDivElement>(".bk-foot");
    const hint = q<HTMLDivElement>(".bk-hint");

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const r = rng(42);

    /* ---- plan ---- */
    const bcx = W / 2, bcy = H / 2;
    const plan = cells.map((c) => {
      const depth = DEPTH[c.kind];
      const center = c.kind === "centerA" || c.kind === "centerB";
      const k = depth === 1 ? 1.2 : depth === 0 ? 1.08 : 1.0;
      const sx = center ? c.cx + (r() - 0.5) * 30 : bcx + (c.cx - bcx) * k + (r() - 0.5) * W * 0.035;
      const sy = center ? c.cy + (r() - 0.5) * 30 : bcy + (c.cy - bcy) * k + (r() - 0.5) * H * 0.045;
      const sgn = r() < 0.5 ? -1 : 1;
      return {
        depth, center, sx, sy,
        s0: center ? 0.42 : depth === 1 ? 0.9 : depth === 0 ? 0.72 : 0.6,
        r0: sgn * (depth === 1 ? 7 + r() * 5 : depth === 0 ? 5 + r() * 4 : 3 + r() * 4),
        b0: depth === 1 ? 3.4 : depth === -1 ? 0.9 : 0,
        amp: 2 + r() * 3, per: 3800 + r() * 2600, ph: r() * Math.PI * 2,
        key: depth * 10 + r() * 5,
        start: 0, dur: 0, land: 0,
        outDelay: r() * 180, outRot: (r() - 0.5) * 22,
        role: ROLE_OF[c.kind] ?? -1,
      };
    });
    const SIL = 520, STAG = 80;
    const order = plan.map((_, i) => i).sort((a, b) => plan[a].key - plan[b].key);
    order.forEach((i, k) => {
      const p = plan[i];
      p.start = SIL + k * STAG;
      p.dur = p.depth === -1 ? 1300 : p.depth === 0 ? 1200 : 1120;
      p.land = p.start + p.dur;
    });
    const TL = Math.max(...plan.map((p) => p.land));
    const DIS0 = TL + 300, DIS1 = DIS0 + 820;
    const BRAND0 = DIS1 - 140, TAG0 = BRAND0 + 360, CTA0 = BRAND0 + 820;
    const T_END = CTA0 + 460;
    const seamT = seams.map((s) => Math.max(plan[s.a].land, plan[s.b].land) - 90);
    const seamLen = glowCore.map((p) => p.getTotalLength());

    pieceEls.forEach((el, i) => {
      el.style.zIndex = String(10 + (plan[i].depth + 1) * 10 + (plan[i].center ? 0 : 1));
      const c = cells[i];
      const d = piecePath(0, 0, c.w, c.h, c.sides, 1, 0, pad, pad);
      clipEls[i].style.clipPath = `path('${d}')`;
      edgePaths[i].forEach((p) => p.setAttribute("d", d));
    });

    /* ring order for the gold lines */
    const ring = cells.filter((c) => !c.kind.startsWith("center"))
      .map((c) => ({ i: c.i, a: Math.atan2(c.cy - bcy, c.cx - bcx) }))
      .sort((a, b) => a.a - b.a).map((o) => o.i);
    const lineInit = ring.map((_, k) => [0.62, 0.5, 0, 0.62, 0.28, 0.6, 0, 0.55, 0.4, 0.15][k % 10]);
    const linePh = ring.map(() => r() * Math.PI * 2);

    /* ---- clock / state ---- */
    let t = reduce || startAt !== "intro" ? T_END : 0;
    let speed = 1;
    let started = t > 0;
    let tq: number | null = startAt === "reg" ? 9000 : null; // transition clock
    let phaseNow: Phase = startAt === "reg" ? "reg" : t >= T_END ? "ready" : "intro";
    setPhase(phaseNow);
    let mx = 0, my = 0, tmx = 0, tmy = 0;
    let hovered: number | null = null;
    const hoverAmt = [0, 0, 0];
    const pushAmt = [0, 0, 0];
    let tc: number | null = null; // role-choice clock
    let chosen = -1;
    let last = performance.now();
    let raf = 0;
    const cache = new Map<object, Record<string, string>>();
    const set = (el: HTMLElement | SVGElement, prop: string, val: string) => {
      let c = cache.get(el);
      if (!c) { c = {}; cache.set(el, c); }
      if (c[prop] === val) return;
      c[prop] = val;
      el.style.setProperty(prop, val);
    };

    const skip = () => {
      if (tq !== null) return;
      if (!started) started = true;
      if (t < T_END) speed = Math.max(speed, (T_END - t) / 420);
    };
    const begin = () => {
      if (tq !== null) return;
      t = Math.max(t, T_END);
      started = true;
      tq = 0;
      tmx = 0; tmy = 0;
      phaseNow = "transition";
      setPhase("transition");
      pieceEls.forEach((el, i) => { el.style.zIndex = plan[i].role >= 0 ? "80" : String(20 + (plan[i].depth + 1) * 10); });
    };
    const choose = (k: number) => {
      if (tc !== null || phaseNow !== "reg") return;
      chosen = k; tc = 0; hovered = null;
    };
    api.current = { begin, hover: (k) => { hovered = k; }, choose };

    const onPointer = (e: PointerEvent) => {
      tmx = (e.clientX / window.innerWidth) * 2 - 1;
      tmy = (e.clientY / window.innerHeight) * 2 - 1;
    };
    const onKey = (e: KeyboardEvent) => {
      if (phaseNow === "intro") skip();
      else if (phaseNow === "ready" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); begin(); }
    };
    const onSkip = () => { if (phaseNow === "intro") skip(); };
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerdown", onSkip, { passive: true });
    window.addEventListener("wheel", onSkip, { passive: true });
    window.addEventListener("touchstart", onSkip, { passive: true });
    window.addEventListener("keydown", onKey);

    /* preload, then start the clock (initial state is already on screen) */
    let alive = true;
    if (!started) {
      const srcs = [...Object.values(PHOTO), ...AVATARS];
      const loads = srcs.map((s) => new Promise<void>((res) => {
        const im = new Image(); im.onload = () => res(); im.onerror = () => res(); im.src = s;
      }));
      Promise.race([Promise.all(loads), new Promise((res) => setTimeout(res, 2200))]).then(() => {
        if (alive) started = true;
      });
    }

    const frame = (now: number) => {
      const dt = Math.min(50, now - last);
      last = now;
      if (started && t < T_END) {
        t = Math.min(T_END, t + dt * speed);
        if (t >= T_END && phaseNow === "intro") { phaseNow = "ready"; setPhase("ready"); }
      }
      if (tq !== null) {
        tq += dt;
        if (tq > 2300 && phaseNow === "transition") { phaseNow = "reg"; setPhase("reg"); }
      }
      if (tc !== null) tc += dt;
      const C = tc ?? -1;
      const interactive = phaseNow === "ready";
      const k = interactive ? 0.055 : 0.08;
      const gx = interactive ? tmx : 0, gy = interactive ? tmy : 0;
      mx += (gx - mx) * k; my += (gy - my) * k;

      const vw = root.clientWidth, vh = root.clientHeight;
      const S = orient === "land" ? Math.min((vw * 0.955) / W, (vh * 0.93) / H) : Math.min((vw * 0.97) / W, (vh * 0.9) / H);
      const ox = (vw - W * S) / 2, oy = (vh - H * S) / 2;
      const vcx = vw / 2, vcy = vh / 2;
      const Q = tq ?? -1;
      const cam = Q >= 0 ? 1 + 0.17 * E_CAM(clamp01(Q / 1900)) : 1;
      const scr = (bx: number, by: number): [number, number] =>
        [vcx + (ox + bx * S - vcx) * cam, vcy + (oy + by * S - vcy) * cam];
      const reg = regGeo(vw, vh);
      if (reg.stacked !== stackedRef) { stackedRef = reg.stacked; setStacked(reg.stacked); }

      /* world tilt (phase 6) */
      set(world, "transform", `perspective(1800px) rotateX(${f2(-my * 2.2)}deg) rotateY(${f2(mx * 3)}deg)`);

      /* board space (unified board + seam glow) */
      const [bsx, bsy] = scr(0, 0);
      set(boardSpace, "transform", `translate(${f2(bsx)}px, ${f2(bsy)}px) scale(${(S * cam).toFixed(5)})`);
      unified.style.setProperty("--mx", f2(mx));
      unified.style.setProperty("--my", f2(my));

      // phase 4 — seams dissolve through a growing feathered mask on the continuous image
      let uOp = 0, mask = "none";
      if (t >= DIS0) {
        uOp = 1;
        if (t < DIS1) {
          const dp = E_IO(clamp01((t - DIS0) / (DIS1 - DIS0)));
          const R = Math.max(2, dp * Math.hypot(W, H) * 0.62);
          const fe = Math.min(W, H) * 0.22;
          mask = `radial-gradient(ellipse ${f2(R * 1.15)}px ${f2(R * 0.82)}px at 50% 50%, #000 ${Math.max(0, 1 - fe / Math.max(R, 1)) * 100}%, transparent 100%)`;
        }
      }
      if (Q >= 0) uOp = 1 - clamp01((Q - 260) / 160);
      set(unified, "opacity", f2(uOp));
      set(unified, "-webkit-mask-image", mask);
      set(unified, "mask-image", mask);

      /* seam glow (phase 3) */
      seams.forEach((_, s) => {
        const g = clamp01((t - seamT[s]) / 720);
        const L = seamLen[s];
        const on = g > 0 && g < 1 && Q < 0;
        const o = on ? Math.sin(Math.PI * g) : 0;
        const off = lerp(L * 0.24, -L, E_IO(g));
        for (const el of [glowCore[s], glowSoft[s]]) {
          set(el, "opacity", f2(o * (el === glowCore[s] ? 0.95 : 0.35)));
          set(el, "stroke-dasharray", `${f2(L * 0.24)} ${f2(L * 2)}`);
          set(el, "stroke-dashoffset", f2(off));
        }
      });

      /* pieces */
      const piecesFade = t > DIS1 ? 1 - clamp01((t - DIS1) / 320) : 1;
      const anchors: { x: number; y: number }[] = [];
      cells.forEach((c, i) => {
        const pl = plan[i];
        const el = pieceEls[i];
        const p = E_ATTRACT(clamp01((t - pl.start) / pl.dur));
        let cx = lerp(pl.sx, c.cx, p), cy = lerp(pl.sy, c.cy, p);
        let [X, Y] = scr(cx, cy);
        const fl = 1 - p;
        X += Math.sin((now / pl.per) * Math.PI * 2 + pl.ph) * pl.amp * fl;
        Y += Math.cos((now / (pl.per * 1.3)) * Math.PI * 2 + pl.ph) * pl.amp * 0.8 * fl;
        let sc = lerp(pl.s0, 1, p) * S * cam;
        let rot = pl.r0 * (1 - p);
        let blur = pl.b0 * Math.pow(1 - p, 1.5);
        let lift = 1 - p;
        let op = pl.center ? clamp01((t - pl.start) / (pl.dur * 0.55)) : 1;
        op *= piecesFade;
        let edgeOp = 1;

        if (Q >= 0) {
          op = Q < 260 ? 0 : 1;
          edgeOp = 0;
          lift = 0;
          if (pl.role >= 0) {
            const tr = reg.rects[pl.role];
            const m = E_IO(clamp01((Q - 320 - pl.role * 90) / 1400));
            let rw = c.w, rh = (rw * tr.h) / tr.w;
            const maxH = c.h + 2 * pad - 6, maxW = c.w + 2 * pad - 6;
            if (rh > maxH) { rh = maxH; rw = (rh * tr.w) / tr.h; }
            if (rw > maxW) { rw = maxW; rh = (rw * tr.h) / tr.w; }
            const rx = (c.w - rw) / 2, ry = (c.h - rh) / 2;
            const sEnd = tr.w / rw;
            const hv = hoverAmt[pl.role] += ((phaseNow === "reg" && hovered === pl.role ? 1 : 0) - hoverAmt[pl.role]) * 0.14;
            // neighbours step 2–3px away from the hovered card
            const pushT = phaseNow === "reg" && hovered !== null && hovered !== pl.role ? Math.sign(pl.role - hovered) * 2.5 : 0;
            const pu = pushAmt[pl.role] += (pushT - pushAmt[pl.role]) * 0.14;
            X = lerp(X, tr.cx, m) + (reg.stacked ? 0 : pu);
            Y = lerp(Y, tr.cy, m) - hv * 6 + (reg.stacked ? pu : 0);
            sc = lerp(sc, sEnd, m) * (1 + 0.035 * Math.sin(Math.PI * m)) * (1 + hv * 0.012);
            rot = 0;
            lift = 0.3 * m + 0.7 * Math.sin(Math.PI * m) + hv * 0.35;
            const d = piecePath(lerp(0, rx, m), lerp(0, ry, m), lerp(c.w, rw, m), lerp(c.h, rh, m), c.sides, 1 - m, (16 / sEnd) * m, pad, pad);
            set(clipEls[i], "clip-path", `path('${d}')`);
            if (C >= 0) {
              if (pl.role === chosen) op = 0; // the journey sheet now carries this card
              else {
                // 180–650ms: neighbours reduce to .94, drift outward from the chosen card, fade away
                const e = E_OUT(clamp01((C - 180) / 470));
                const dir = Math.sign(pl.role - chosen);
                if (reg.stacked) Y += dir * vh * 0.16 * e; else X += dir * vw * 0.14 * e;
                sc *= 1 - 0.06 * e;
                op *= 1 - e;
              }
            }
            const rl = roleLayers[i], ri = roleInners[i];
            if (rl && ri) {
              set(rl, "left", `${f2(pad + rx)}px`); set(rl, "top", `${f2(pad + ry)}px`);
              set(rl, "width", `${f2(rw)}px`); set(rl, "height", `${f2(rh)}px`);
              set(rl, "opacity", f2(clamp01((m - 0.28) / 0.42)));
              set(ri, "width", `${f2(tr.w)}px`); set(ri, "height", `${f2(tr.h)}px`);
              set(ri, "transform", `scale(${(rw / tr.w).toFixed(5)})`);
              set(ri, "--r", `${f2(16)}px`);
            }
          } else {
            const e = E_CAM(clamp01((Q - 250 - pl.outDelay) / 1350));
            if (pl.center) {
              sc *= 1 + 1.9 * e;
              op *= 1 - e;
            } else {
              let dx = c.cx - bcx, dy = c.cy - bcy;
              const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
              const dist = Math.max(vw, vh) * 0.95 * Math.pow(e, 1.25);
              X += dx * dist; Y += dy * dist;
              rot += pl.outRot * e;
              sc *= 1 + 0.35 * e;
              blur = 7 * Math.pow(e, 1.4);
              lift = 0.9 * e;
            }
          }
        }

        const pvx = pad + c.w / 2, pvy = pad + c.h / 2;
        set(el, "transform", `translate3d(${f2(X)}px, ${f2(Y)}px, 0) rotate(${f2(rot)}deg) scale(${sc.toFixed(5)}) translate(${-pvx}px, ${-pvy}px)`);
        set(el, "opacity", f2(op));
        set(el, "visibility", op <= 0.001 ? "hidden" : "visible");
        const b = Math.round(blur * 10) / 10;
        const lq = Math.round(lift * 40) / 40;
        set(el, "filter", `${b > 0.05 ? `blur(${b}px) ` : ""}drop-shadow(0 ${f2(1 + 16 * lq)}px ${f2(2 + 22 * lq)}px rgba(58,40,20,${f2(0.14 + 0.16 * lq)}))`);
        set(edgeEls[i], "opacity", f2(edgeOp));

        if (!pl.center) {
          const half = Math.min(c.w, c.h) / 2 * 0.86 * (sc / (S * cam || 1)) * S * cam;
          let ax = scr(bcx, bcy)[0] - X, ay = scr(bcx, bcy)[1] - Y;
          const al = Math.hypot(ax, ay) || 1; ax /= al; ay /= al;
          anchors[i] = { x: X + ax * half + mx * 2, y: Y + ay * half + my * 2 };
        }
      });

      /* gold lines — loose while floating, settling after the reveal */
      const settle = E_IO(clamp01((t - BRAND0) / 1600));
      const A = lerp(15, 1.2, settle) * Math.max(0.5, S);
      const linesFade = Q >= 0 ? 1 - clamp01(Q / 520) : 1;
      const n = ring.length;
      const P = ring.map((i) => anchors[i]);
      for (let k = 0; k < n; k++) {
        const p0 = P[(k - 1 + n) % n], p1 = P[k], p2 = P[(k + 1) % n], p3 = P[(k + 2) % n];
        let c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
        let c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
        const sl = Math.hypot(p2.x - p1.x, p2.y - p1.y) || 1;
        const nx = -(p2.y - p1.y) / sl, ny = (p2.x - p1.x) / sl;
        const w1 = Math.sin(now * 0.00055 + linePh[k]) * A, w2 = Math.cos(now * 0.00047 + linePh[k] * 1.7) * A;
        c1x += nx * w1; c1y += ny * w1; c2x += nx * w2; c2y += ny * w2;
        linePaths[k].setAttribute("d", `M${f2(p1.x)} ${f2(p1.y)}C${f2(c1x)} ${f2(c1y)} ${f2(c2x)} ${f2(c2y)} ${f2(p2.x)} ${f2(p2.y)}`);
        const o = lerp(lineInit[k], 0.7, settle) * linesFade * clamp01(0.6 + t / 300);
        set(linePaths[k], "opacity", f2(o));
        lineNodes[k].setAttribute("cx", f2(p1.x));
        lineNodes[k].setAttribute("cy", f2(p1.y));
        set(lineNodes[k], "opacity", f2(Math.max(o, lineInit[(k - 1 + n) % n] * linesFade) * 0.9));
      }

      /* brand (phase 5) */
      const bf = Math.max(40, Math.min(116, 96 * S));
      set(brand, "--bf", `${f2(bf)}px`);
      set(brand, "--tf", `${f2(Math.max(10, Math.min(14, 13.5 * S)))}px`);
      let [BX, BY] = scr(bcx, bcy);
      BX -= mx * 3; BY -= my * 2;
      let bScale = 1;
      let tagOp = 1;
      if (Q >= 0) {
        const bq = E_IO(clamp01(Q / 1150));
        BX = lerp(BX, vw / 2, bq); BY = lerp(BY, 40, bq);
        bScale = lerp(1, 26 / bf, bq);
        tagOp = 1 - clamp01(Q / 360);
      }
      if (C >= 0) {
        // the wordmark slides to the top-left identity position of the registration frame
        const cq = E_IO(clamp01(C / 700));
        BX = lerp(BX, 36 + 46, cq); BY = lerp(BY, 34, cq);
        bScale = lerp(bScale, 20 / bf, cq);
      }
      set(brand, "transform", `translate(${f2(BX)}px, ${f2(BY)}px) translate(-50%, -50%) scale(${bScale.toFixed(4)})`);
      set(brand, "opacity", f2(C >= 0 ? 1 - clamp01((C - 420) / 260) : 1));
      const wr = E_OUT(clamp01((t - BRAND0) / 1000));
      const ls = lerp(0.46, 0.06, E_OUT(clamp01((t - BRAND0) / 1500)));
      set(word, "transform", `translateY(${f2((1 - wr) * 108)}%)`);
      set(word, "letter-spacing", `${ls.toFixed(3)}em`);
      tagLines.forEach((el, k) => {
        const p = E_OUT(clamp01((t - TAG0 - k * 130) / 900));
        set(el, "transform", `translateY(${f2((1 - p) * 110)}%)`);
        set(el, "letter-spacing", `${lerp(0.62, 0.3, E_OUT(clamp01((t - TAG0 - k * 130) / 1300))).toFixed(3)}em`);
        set(el, "opacity", f2(tagOp));
      });
      const cp = E_OUT(clamp01((t - CTA0) / 650));
      set(cta, "opacity", f2(cp * tagOp));
      set(cta, "transform", `translateY(${f2((1 - cp) * 10)}px)`);
      set(cta, "pointer-events", cp > 0.6 && Q < 0 ? "auto" : "none");

      /* footers + skip hint */
      const fo = E_OUT(clamp01((t - BRAND0 - 400) / 900)) * (Q >= 0 ? 1 - clamp01(Q / 400) : 1);
      foot.forEach((el) => set(el, "opacity", f2(fo * 0.9)));
      const ho = clamp01((t - 900) / 500) * (1 - clamp01((t - BRAND0 + 400) / 400));
      set(hint, "opacity", f2(started ? ho * 0.75 : 0));

      /* satellites — out-of-focus foreground fragments */
      satEls.forEach((el, k) => {
        const s = SATS[k];
        const size = Math.min(vw, vh) * s.s * (orient === "port" ? 1.6 : 1);
        let x = s.x * vw, y = s.y * vh;
        x += Math.sin(now / 5200 + k * 1.3) * 5 + mx * 14 * s.d;
        y += Math.cos(now / 6100 + k) * 4 + my * 10 * s.d;
        const appear = clamp01(0.35 + t / 900);
        let o = 0.82 * appear, rr = s.r, ss = 1, bb = s.b;
        if (Q >= 0) {
          const e = E_CAM(clamp01((Q - 120 - k * 40) / 1200));
          let dx = x - vcx, dy = y - vcy; const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
          x += dx * Math.max(vw, vh) * 0.7 * e; y += dy * Math.max(vw, vh) * 0.7 * e;
          ss = 1 + 0.6 * e; rr += 10 * e; bb += 6 * e; o *= 1 - e * 0.6;
        }
        set(el, "width", `${f2(size)}px`); set(el, "height", `${f2(size)}px`);
        set(el, "transform", `translate(${f2(x - size / 2)}px, ${f2(y - size / 2)}px) rotate(${f2(rr)}deg) scale(${f2(ss)})`);
        set(el, "filter", `blur(${f2(bb)}px)`);
        set(el, "opacity", f2(o));
      });

      /* registration chrome */
      const ro = Q >= 0 ? E_OUT(clamp01((Q - 1150) / 700)) : 0;
      set(regHead, "top", `${f2(reg.titleTop)}px`);
      const co = C >= 0 ? 1 - clamp01(C / 260) : 1;
      set(regHead, "opacity", f2(ro * co));
      set(regHead, "transform", `translateY(${f2((1 - ro) * 14)}px)`);
      set(regActions, "top", `${f2(reg.actionsTop)}px`);
      set(regActions, "opacity", f2((Q >= 0 ? E_OUT(clamp01((Q - 1500) / 700)) : 0) * co));

      raf = requestAnimationFrame(frame);
    };
    let stackedRef: boolean | null = null;
    raf = requestAnimationFrame(frame);
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerdown", onSkip);
      window.removeEventListener("wheel", onSkip);
      window.removeEventListener("touchstart", onSkip);
      window.removeEventListener("keydown", onKey);
      api.current = null;
    };
  }, [geo, orient, startAt]);

  const pick = (role: number, inner: Element | null) => {
    if (phase !== "reg" || selected !== null || !inner) return;
    const photo = inner.querySelector(".bk-role-photo");
    if (!photo) return;
    setSelected(role);
    onChoose({ role, card: inner.getBoundingClientRect(), photo: photo.getBoundingClientRect(), stacked });
    api.current?.choose(role);
  };
  const { W, H, pad, cells, seams } = geo;
  return (
    <div ref={rootRef} className={`bk-root bk-${phase}${stacked ? " bk-stacked" : ""}`}>
      <div className="bk-world">
        {/* pieces of the puzzle — each is a clipped window onto the same continuous composition */}
        {cells.map((c) => {
          const role = ROLE_OF[c.kind];
          return (
            <div key={c.i} className="bk-piece" style={{ width: c.w + 2 * pad, height: c.h + 2 * pad }}>
              <div className="bk-piece-clip">
                <div className="bk-piece-board" style={{ left: pad - c.x, top: pad - c.y }}>
                  <BoardContent geo={geo} />
                </div>
                <svg className="bk-piece-edge" width={c.w + 2 * pad} height={c.h + 2 * pad} aria-hidden>
                  <path className="hi" /><path className="lo" />
                </svg>
                {role !== undefined && (
                  <div className="bk-role-layer"
                    onPointerEnter={() => api.current?.hover(role)}
                    onPointerLeave={() => api.current?.hover(null)}
                    onClick={(e) => pick(role, e.currentTarget.querySelector(".bk-role-inner"))}>
                    <div className={`bk-role-inner${selected === role ? " is-selected" : ""}`}
                      role="button" tabIndex={phase === "reg" && selected === null ? 0 : -1} aria-disabled={phase !== "reg" || selected !== null} aria-pressed={selected === role}
                      aria-label={`${ROLES[role].title} — ${ROLES[role].kicker}`}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(role, e.currentTarget); } }}>
                      <div className="bk-role-photo"><img src={ROLES[role].photo} alt="" draggable={false} /></div>
                      <div className="bk-role-body">
                        <span className="bk-kicker">{ROLES[role].kicker}</span>
                        <span className="bk-role-title">{ROLES[role].title}</span>
                        <span className="bk-role-text">{ROLES[role].text}</span>
                        <span className="bk-role-arrow" aria-hidden>
                          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M5 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        <div className="bk-boardspace" style={{ width: W, height: H }}>
          <svg className="bk-glow" width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
            {seams.map((s, k) => <path key={`s${k}`} className="soft" d={s.d} />)}
            {seams.map((s, k) => <path key={`c${k}`} className="core" d={s.d} />)}
          </svg>
          <div className="bk-unified"><BoardContent geo={geo} /></div>
        </div>

        <svg className="bk-lines" aria-hidden>
          {cells.filter((c) => !c.kind.startsWith("center")).map((c) => <path key={c.i} />)}
          {cells.filter((c) => !c.kind.startsWith("center")).map((c) => <circle key={c.i} r="2.2" />)}
        </svg>

        {sats.map((s, k) => (
          <div key={k} className="bk-sat" aria-hidden>
            <svg viewBox="-18 -18 136 136" width="100%" height="100%">
              <defs><clipPath id={`bk-sat-${k}`}><path d={s.d} /></clipPath></defs>
              <image href={s.img} x="-18" y="-18" width="136" height="136" preserveAspectRatio="xMidYMid slice" clipPath={`url(#bk-sat-${k})`} />
            </svg>
          </div>
        ))}

        <div className="bk-brand">
          <h1 className="bk-wordmark"><span className="bk-word">BUKER</span></h1>
          <p className="bk-tag">
            <span className="bk-tag-line"><span>Нужные люди.</span></span>
            <span className="bk-tag-line"><span>Подходящее место.</span></span>
            <span className="bk-tag-line"><span>Один клик.</span></span>
          </p>
          <div className="bk-cta-wrap">
            <button type="button" className="bk-cta" onClick={() => api.current?.begin()}>
              <span>Начать</span>
              <svg className="bk-cta-edge" viewBox="0 0 180 48" width="180" height="48" aria-hidden>
                <rect className="base" x="0.75" y="0.75" width="178.5" height="46.5" rx="23.25" pathLength="100" />
                <rect className="run" x="0.75" y="0.75" width="178.5" height="46.5" rx="23.25" pathLength="100" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div className="bk-vignette" aria-hidden />
      <div className="bk-foot bk-foot-l">People · Places · Moments · Forever</div>
      <div className="bk-foot bk-foot-r">От идеи до реального события</div>
      <div className="bk-hint">Нажмите, чтобы пропустить</div>

      <div className="bk-reg-head">
        <h2>Кем вы будете в&nbsp;Buker?</h2>
        <p>Выберите роль — с неё начнётся ваша регистрация.</p>
      </div>
      <div className="bk-reg-actions">
        <span className="bk-pick-hint">Нажмите на карточку, чтобы продолжить</span>
        <button type="button" className="bk-replay" onClick={onReplay}>Посмотреть интро ещё раз</button>
      </div>
    </div>
  );
}


export default function LiveSceneHome() {
  const [orient, setOrient] = useState<Orientation>("land");
  const [mounted, setMounted] = useState(false);
  const [run, setRun] = useState(0);
  const phaseRef = useRef<Phase>("intro");
  const recoveryRef = useRef<ReturnType<typeof installSceneRecovery> | null>(null);
  const [startAt, setStartAt] = useState<StartAt>("intro");
  const onPhase = useCallback((phase: Phase) => { phaseRef.current = phase; }, []);
  useEffect(() => {
    const resize = () => {
      const next = window.innerWidth / window.innerHeight < 0.95 || window.innerWidth < 760 ? "port" : "land";
      setOrient(cur => { if (cur !== next) setStartAt(phaseRef.current === "reg" || phaseRef.current === "transition" ? "reg" : "ready"); return next; });
    };
    setOrient(window.innerWidth / window.innerHeight < 0.95 || window.innerWidth < 760 ? "port" : "land");
    setMounted(true);
    const recovery = installSceneRecovery(window, mode => {
      phaseRef.current = mode === "reg" ? "reg" : "ready";
      setStartAt(mode);
      setRun(value => value + 1);
      setMounted(true);
    });
    recoveryRef.current = recovery;
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      recovery.dispose();
      recoveryRef.current = null;
    };
  }, []);
  const onChoose = useCallback((info: ChooseInfo) => {
    const roles = ["customer", "artist", "venue"];
    const next = info.role === 0 ? "/events/new" : info.role === 1 ? "/cabinet/performer" : "/cabinet/venue";
    recoveryRef.current?.markRoleNavigation();
    window.location.assign(`/login?mode=register&role=${roles[info.role]}&next=${encodeURIComponent(next)}`);
  }, []);
  return <main className="bk-live-home" data-release="scene01-v5-live">
    {mounted && <Scene key={`${orient}-${run}`} orient={orient} startAt={startAt} onPhase={onPhase} onChoose={onChoose}
      onReplay={() => { recoveryRef.current?.clearReturn(); phaseRef.current = "intro"; setStartAt("intro"); setRun(n => n + 1); }} />}
    <nav className="bk-live-nav" aria-label="Основная навигация" onKeyDown={event => event.stopPropagation()}>
      <a href="/search?kind=artist">Артисты</a><a href="/search?kind=venue">Площадки</a><a href="/events/new">Создать событие</a><a href="/login">Войти</a>
    </nav>
    <noscript><div className="bk-live-fallback"><h1>Букер</h1><p>Артисты и площадки для вашего события.</p><a href="/search">Открыть каталог</a></div></noscript>
    <a className="bk-live-legal" href="/legal" onKeyDown={event => event.stopPropagation()}>Пилот · Платежи отключены · Правила</a>
  </main>;
}
