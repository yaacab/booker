/* M04 · round jigsaw engine (SVG).
   One centre disc ("Моё событие") + seven equal ring sectors with symmetric tabs.
   The engine only draws and animates; all state lives in React (M04Puzzle). */

export type PieceId = "format" | "date" | "guests" | "artist" | "venue" | "rider" | "budget";
export const RING: PieceId[] = ["format", "date", "guests", "artist", "venue", "rider", "budget"];
export const PIECE_LABEL: Record<PieceId, string> = {
  format: "Формат", date: "Дата и город", guests: "Гости", artist: "Артист",
  venue: "Площадка", rider: "Райдер", budget: "Бюджет",
};

export type Face =
  | { kind: "photo"; img: string; value: string; label?: string }
  | { kind: "collage"; imgs: string[]; value: string; label?: string }
  | { kind: "text"; text: string; sub?: string; label?: string };

const NS = "http://www.w3.org/2000/svg";
const C0: [number, number] = [360, 305];
const R0 = 165, R1 = 330, N = 7, GAP = 16, FS = 1.3;
export const VIEW = { x: -70, y: -60, w: 860, h: 730 };
export const FINALE_IMAGE = "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&fit=crop&w=1600&q=75";
const IMG_BOX = { x: -90, y: -90, w: 900, h: 790 };

const TH = (k: number) => ((-90 - 180 / N + (k * 360) / N) * Math.PI) / 180;
const pol = (r: number, a: number): [number, number] => [C0[0] + r * Math.cos(a), C0[1] + r * Math.sin(a)];
const f = (n: number) => Math.round(n * 100) / 100;
const KT = 0.1;
const KN: [number, number][] = [[0, 0], [0.2, 0], [0.5, -KT], [0.5 - KT, KT], [0.5 - 2 * KT, 3 * KT], [0.5 + 2 * KT, 3 * KT], [0.5 + KT, KT], [0.5, -KT], [0.8, 0], [1, 0]];
const RAD: [number, number][][] = [], ARC: [number, number][][] = [];
for (let k = 0; k < N; k++) {
  const a = TH(k), L = R1 - R0, fl = k % 2 ? 1 : -1, dx = Math.cos(a), dy = Math.sin(a);
  RAD.push(KN.map(([u, v]) => [C0[0] + dx * (R0 + u * L) - dy * v * L * fl, C0[1] + dy * (R0 + u * L) + dx * v * L * fl]));
  const a0 = TH(k), a1 = TH(k + 1), La = R0 * (a1 - a0), fa = k % 2 ? -1 : 1;
  ARC.push(KN.map(([u, v]) => pol(R0 + v * La * fa, a0 + u * (a1 - a0))));
}
const ps = (p: [number, number]) => `${f(p[0])} ${f(p[1])}`;
const seg = (q: [number, number][]) => `C${ps(q[1])} ${ps(q[2])} ${ps(q[3])}C${ps(q[4])} ${ps(q[5])} ${ps(q[6])}C${ps(q[7])} ${ps(q[8])} ${ps(q[9])}`;
type Cell = { x: number; y: number; w: number; h: number; c: [number, number]; k: number };
const bbox = (pts: [number, number][]) => {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
};
const CELLS = {} as Record<PieceId, Cell>;
RING.forEach((id, k) => {
  const pts = [...ARC[k], ...RAD[k], ...RAD[(k + 1) % N]];
  for (let i = 0; i <= 8; i++) pts.push(pol(R1, TH(k) + (i / 8) * (TH(k + 1) - TH(k))));
  CELLS[id] = { ...bbox(pts), c: pol((R0 + R1) / 2 + 4, (TH(k) + TH(k + 1)) / 2), k };
});
function piecePath(id: PieceId | "core") {
  if (id === "core") return `M${ps(ARC[0][0])}` + ARC.map(seg).join("") + "Z";
  const k = CELLS[id].k, k1 = (k + 1) % N, o = pol(R1, TH(k));
  return `M${ps(ARC[k][0])}` + seg(ARC[k]) + seg(RAD[k1]) + `A${R1} ${R1} 0 0 0 ${ps(o)}` + seg([...RAD[k]].reverse()) + "Z";
}
const OFF = (id: PieceId): [number, number] => {
  const [cx, cy] = CELLS[id].c, dx = cx - C0[0], dy = cy - C0[1], L = Math.hypot(dx, dy) || 1;
  return [(dx / L) * GAP, (dy / L) * GAP];
};
const centerOf = (id: PieceId): [number, number] => { const c = CELLS[id]; return [c.x + c.w / 2, c.y + c.h / 2]; };

type Pose = { x: number; y: number; r: number; s: number };
type Piece = { g: SVGGElement; bob: SVGGElement; face: SVGGElement; cont: SVGImageElement; seam: SVGPathElement; bevel: SVGPathElement; warn: SVGGElement | null; pose: Pose; filled: boolean };

function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, parent?: Element): SVGElementTagNameMap[K] {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  if (parent) parent.appendChild(e);
  return e;
}
function txt(parent: Element, x: number, y: number, s: string, cls: string, size: number, anchor = "middle", weight = 400) {
  const t = el("text", { x: f(x), y: f(y), class: cls, "font-size": f(size), "text-anchor": anchor, "font-weight": weight }, parent);
  t.textContent = s;
  return t;
}
export function wrap(s: string, max: number) {
  const out: string[] = []; let cur = "";
  for (const w of s.split(" ")) { if ((cur + " " + w).trim().length > max && cur) { out.push(cur); cur = w; } else cur = (cur + " " + w).trim(); }
  if (cur) out.push(cur);
  return out;
}
const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export class M04Engine {
  svg: SVGSVGElement; uid: string; defs: SVGDefsElement; board: SVGGElement; pieces = {} as Record<PieceId, Piece>;
  socks = {} as Record<PieceId, SVGPathElement>; core: SVGGElement; coreBob: SVGGElement; coreCont: SVGImageElement; coreBev: SVGPathElement;
  outLine: SVGCircleElement; outHalo: SVGCircleElement; pieceG: SVGGElement; onPiece?: (id: PieceId) => void;

  constructor(svg: SVGSVGElement, uid: string) {
    this.svg = svg; this.uid = uid;
    svg.setAttribute("viewBox", `${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`);
    this.defs = el("defs", {}, svg);
    const d = this.defs;
    const sh = el("linearGradient", { id: `${uid}-sh`, x1: 0, y1: 0, x2: 0, y2: 1 }, d);
    el("stop", { offset: "35%", "stop-color": "#2a170b", "stop-opacity": 0 }, sh); el("stop", { offset: "100%", "stop-color": "#2a170b", "stop-opacity": 0.66 }, sh);
    const bv = el("linearGradient", { id: `${uid}-bevel`, x1: 0, y1: 0, x2: 1, y2: 1 }, d);
    [["0%", "#fff", 0.85], ["45%", "#fff", 0], ["60%", "#5a3010", 0], ["100%", "#5a3010", 0.35]].forEach(([o, c, a]) => el("stop", { offset: o, "stop-color": c, "stop-opacity": a }, bv));
    const pp = el("linearGradient", { id: `${uid}-paper`, x1: 0, y1: 0, x2: 0.6, y2: 1 }, d);
    el("stop", { offset: "0%", "stop-color": "#fffdf8" }, pp); el("stop", { offset: "100%", "stop-color": "#f5e6d0" }, pp);
    const soft = el("filter", { id: `${uid}-soft`, x: "-50%", y: "-80%", width: "200%", height: "260%" }, d); el("feGaussianBlur", { stdDeviation: 14 }, soft);
    this.board = el("g", {}, svg);
    const sockG = el("g", { class: "m4-socks" }, this.board);
    for (const id of RING) { const [ox, oy] = OFF(id); this.socks[id] = el("path", { d: piecePath(id), transform: `translate(${f(ox)} ${f(oy)})`, class: "m4-sock" }, sockG); }
    this.pieceG = el("g", {}, this.board);
    // centre disc
    this.core = el("g", { class: "m4-pc" }, this.pieceG);
    this.coreBob = el("g", { class: "m4-bob", style: "animation-duration:8s" }, this.core);
    const ccp = el("clipPath", { id: `${uid}-c-core` }, d); el("path", { d: piecePath("core") }, ccp);
    const cg = el("g", { "clip-path": `url(#${uid}-c-core)` }, this.coreBob);
    const cb = bbox(ARC.flat());
    el("rect", { x: cb.x - 90, y: cb.y - 90, width: cb.w + 180, height: cb.h + 180, fill: `url(#${uid}-paper)`, opacity: 0.95 }, cg);
    this.coreCont = el("image", { href: FINALE_IMAGE, ...IMG_BOX, preserveAspectRatio: "xMidYMid slice", opacity: 0, class: "m4-muted" }, cg);
    this.coreBev = el("path", { d: piecePath("core"), class: "m4-bevel", stroke: `url(#${uid}-bevel)` }, cg);
    for (const id of RING) this.buildPiece(id);
    this.outHalo = el("circle", { cx: C0[0], cy: C0[1], r: R1 + GAP + 5, fill: "none", stroke: "#ffd98f", "stroke-width": 22, opacity: 0, filter: `url(#${uid}-soft)` }, this.board);
    this.outLine = el("circle", { cx: C0[0], cy: C0[1], r: R1 + GAP + 5, fill: "none", stroke: "#d6ae63", "stroke-width": 2.6, "stroke-linecap": "round", opacity: 0, transform: `rotate(-90 ${C0[0]} ${C0[1]})` }, this.board);
  }

  private buildPiece(id: PieceId) {
    const c = CELLS[id], d = piecePath(id);
    const cp = el("clipPath", { id: `${this.uid}-c-${id}` }, this.defs); el("path", { d }, cp);
    const g = el("g", { class: "m4-pc", role: "button", tabindex: -1, "aria-label": `${PIECE_LABEL[id]} — изменить` }, this.pieceG);
    const bob = el("g", { class: "m4-bob" }, g);
    bob.style.animationDuration = `${5.5 + (c.k * 0.7) % 3}s`; bob.style.animationDelay = `${-c.k * 0.9}s`;
    const cg = el("g", { "clip-path": `url(#${this.uid}-c-${id})` }, bob);
    el("rect", { x: c.x - 90, y: c.y - 90, width: c.w + 180, height: c.h + 180, fill: "#f4eee5" }, cg);
    const face = el("g", { class: "m4-face" }, cg);
    const cont = el("image", { href: FINALE_IMAGE, ...IMG_BOX, preserveAspectRatio: "xMidYMid slice", opacity: 0, class: "m4-muted" }, cg);
    const bevel = el("path", { d, class: "m4-bevel", stroke: `url(#${this.uid}-bevel)` }, cg);
    const seam = el("path", { d, class: "m4-seam" }, bob);
    const [cx, cy] = centerOf(id);
    const p: Piece = { g, bob, face, cont, seam, bevel, warn: null, pose: { x: cx, y: cy, r: 0, s: 1 }, filled: false };
    this.pieces[id] = p;
    g.style.opacity = "0";
    g.addEventListener("click", () => { if (p.filled) this.onPiece?.(id); });
    g.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter" || (e as KeyboardEvent).key === " ") { e.preventDefault(); if (p.filled) this.onPiece?.(id); } });
    this.place(id, this.sockPose(id));
  }

  /* ---------- faces ---------- */
  setFace(id: PieceId, F: Face) {
    const p = this.pieces[id], c = CELLS[id], [cx, cy] = c.c, fs = FS, fc = p.face;
    while (fc.firstChild) fc.removeChild(fc.firstChild);
    const lbl = (F.label || PIECE_LABEL[id]).toUpperCase();
    if (F.kind === "photo" || F.kind === "collage") {
      const imgs = F.kind === "photo" ? [F.img] : F.imgs, X = c.x - 60, W = c.w + 120;
      imgs.forEach((src, k) => {
        const sv = el("svg", { x: f(X + (k * W) / imgs.length), y: f(c.y - 60), width: f(W / imgs.length), height: f(c.h + 120), overflow: "hidden" }, fc);
        el("image", { href: src, x: 0, y: 0, width: f(W / imgs.length), height: f(c.h + 120), preserveAspectRatio: "xMidYMid slice" }, sv);
        if (k) el("line", { x1: f(X + (k * W) / imgs.length), x2: f(X + (k * W) / imgs.length), y1: c.y - 60, y2: c.y + c.h + 60, stroke: "rgba(233,194,122,.8)", "stroke-width": 1.4 }, fc);
      });
      el("ellipse", { cx: f(cx), cy: f(cy + 4 * fs), rx: f(c.w * 0.38), ry: f(32 * fs), fill: "rgba(36,18,8,.46)", filter: `url(#${this.uid}-soft)` }, fc);
      txt(fc, cx, cy - 10 * fs, F.kind === "collage" ? `АРТИСТЫ · ${imgs.length}` : lbl, "m4-t-k", 9.5 * fs);
      wrap(F.value, F.kind === "collage" ? 12 : 15).slice(0, 2).forEach((l, i) => txt(fc, cx, cy + 12 * fs + i * 19 * fs, l, "m4-t-v", (F.kind === "collage" ? 16 : 19) * fs));
    } else {
      el("rect", { x: c.x - 60, y: c.y - 60, width: c.w + 120, height: c.h + 120, fill: `url(#${this.uid}-paper)` }, fc);
      txt(fc, cx, cy - 18 * fs, lbl, "m4-t-k m4-dark", 9.5 * fs);
      txt(fc, cx, cy + 10 * fs, F.text, "m4-t-big", (F.text.length > 7 ? 22 : 28) * fs);
      el("circle", { cx: f(cx), cy: f(cy + 21 * fs), r: 1.8 * fs, fill: "#c9a467" }, fc);
      if (F.sub) txt(fc, cx, cy + 36 * fs, F.sub.toUpperCase(), "m4-t-sub", 8.5 * fs);
    }
  }

  /* ---------- poses ---------- */
  private tf(id: PieceId, P: Pose) { const [cx, cy] = centerOf(id); return `translate(${f(P.x)}px,${f(P.y)}px) rotate(${f(P.r)}deg) scale(${f(P.s)}) translate(${-cx}px,${-cy}px)`; }
  sockPose(id: PieceId, gap = 1): Pose { const [cx, cy] = centerOf(id), [ox, oy] = OFF(id); return { x: cx + ox * gap, y: cy + oy * gap, r: 0, s: 1 }; }
  private place(id: PieceId, P: Pose) { const p = this.pieces[id]; p.pose = P; p.g.style.transform = this.tf(id, P); }
  private async anim(e: Element, frames: Keyframe[], dur: number, ease = "cubic-bezier(.2,.7,.2,1)", delay = 0) {
    if (reduced()) { const last = { ...frames[frames.length - 1] } as Record<string, unknown>; delete last.offset; for (const k in last) (e as HTMLElement).style.setProperty(k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase()), String(last[k])); return; }
    const a = e.animate(frames, { duration: dur, easing: ease, delay, fill: "forwards" });
    try { await a.finished; } catch { return; }
    try { a.commitStyles(); } catch { /* detached */ }
    a.cancel();
  }
  private async move(id: PieceId, to: Pose, dur: number, o: { arc?: number; over?: boolean; ease?: string } = {}) {
    const p = this.pieces[id], from = p.pose, fr: Keyframe[] = [{ transform: this.tf(id, from) }];
    if (o.arc) fr.push({ offset: 0.5, transform: this.tf(id, { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - o.arc, r: (from.r + to.r) / 2, s: Math.max(from.s, to.s) * 1.06 }) });
    if (o.over) fr.push({ offset: 0.86, transform: this.tf(id, { ...to, s: to.s * 1.035 }) });
    fr.push({ transform: this.tf(id, to) });
    p.pose = to;
    await this.anim(p.g, fr, dur, o.ease);
  }
  /** screen rect → board coordinates */
  toBoard(sx: number, sy: number): [number, number] {
    const m = this.svg.getScreenCTM(); if (!m) return [C0[0], C0[1]];
    const pt = new DOMPoint(sx, sy).matrixTransform(m.inverse()); return [pt.x, pt.y];
  }
  boardScale() { const m = this.svg.getScreenCTM(); return m ? m.a : 1; }
  screenRectOfBoard() { const m = this.svg.getScreenCTM(); if (!m) return null; const p0 = new DOMPoint(IMG_BOX.x, IMG_BOX.y).matrixTransform(m); return { x: p0.x, y: p0.y, w: IMG_BOX.w * m.a, h: IMG_BOX.h * m.d }; }
  centerScreen() { const m = this.svg.getScreenCTM(); if (!m) return null; const p = new DOMPoint(C0[0], C0[1]).matrixTransform(m); return { x: p.x, y: p.y, r: (R1 + 2) * m.a, core: R0 * m.a }; }

  /* ---------- state changes ---------- */
  show(id: PieceId, F: Face) { const p = this.pieces[id]; this.setFace(id, F); p.filled = true; p.g.style.opacity = "1"; p.g.setAttribute("tabindex", "0"); this.place(id, this.sockPose(id)); this.socks[id].classList.remove("is-hint"); this.syncFloat(id); }
  hide(id: PieceId) { const p = this.pieces[id]; p.filled = false; p.g.style.opacity = "0"; p.g.setAttribute("tabindex", "-1"); this.place(id, this.sockPose(id)); this.setWarn(id, null); }
  private syncFloat(id: PieceId) { this.pieces[id].bob.classList.toggle("is-still", false); }
  hint(id: PieceId, on: boolean) { this.socks[id].classList.toggle("is-hint", on); }

  /** a carousel card (screen rect) becomes this piece and flies home */
  async flyIn(id: PieceId, F: Face, from: DOMRect | null) {
    const p = this.pieces[id], wasFilled = p.filled;
    if (wasFilled || !from || reduced()) {
      if (wasFilled) { await this.anim(p.face, [{ opacity: 1 }, { opacity: 0.12 }], 140); this.setFace(id, F); await this.anim(p.face, [{ opacity: 0.12 }, { opacity: 1 }], 200); }
      else this.show(id, F);
      p.g.classList.remove("is-lift");
      await this.move(id, this.sockPose(id), 320, { over: true });
      void this.glow(id); return;
    }
    this.setFace(id, F); p.filled = true; p.g.setAttribute("tabindex", "0");
    const [bx, by] = this.toBoard(from.x + from.width / 2, from.y + from.height / 2);
    const s = Math.min(1.6, from.width / (CELLS[id].w * this.boardScale()));
    this.place(id, { x: bx, y: by, r: 0, s }); p.g.classList.add("is-lift");
    p.g.style.opacity = "1";
    await this.anim(p.g, [{ opacity: 0 }, { opacity: 1 }], 220);
    await this.move(id, this.sockPose(id), 780, { arc: 90, over: true, ease: "cubic-bezier(.25,.75,.25,1)" });
    p.g.classList.remove("is-lift"); this.socks[id].classList.remove("is-hint");
    await this.glow(id);
  }
  /** an extra artist: a copy flies in and merges into the existing piece; the puzzle outline glows */
  async mergeIn(id: PieceId, single: Face, merged: Face, from: DOMRect | null) {
    const p = this.pieces[id];
    if (from && !reduced()) {
      const old = p.face.cloneNode(true);
      this.setFace(id, single);
      const clone = p.g.cloneNode(true) as SVGGElement; clone.removeAttribute("role"); clone.setAttribute("aria-hidden", "true");
      this.pieceG.appendChild(clone);
      p.face.replaceWith(old as SVGGElement); p.face = old as SVGGElement;
      const [bx, by] = this.toBoard(from.x + from.width / 2, from.y + from.height / 2), to = this.sockPose(id);
      const s0 = Math.min(1.6, from.width / (CELLS[id].w * this.boardScale())), A = { x: bx, y: by, r: 0, s: s0 };
      clone.style.transform = this.tf(id, A); clone.classList.add("is-lift");
      await this.anim(clone, [{ opacity: 0 }, { opacity: 1 }], 220);
      await this.anim(clone, [{ transform: this.tf(id, A) }, { offset: 0.5, transform: this.tf(id, { x: (A.x + to.x) / 2, y: (A.y + to.y) / 2 - 80, r: 0, s: s0 * 0.7 }) }, { offset: 0.86, transform: this.tf(id, { ...to, s: 1.035 }) }, { transform: this.tf(id, to) }], 820, "cubic-bezier(.25,.75,.25,1)");
      await this.anim(p.face, [{ opacity: 1 }, { opacity: 0.2 }], 140);
      this.setFace(id, merged); clone.remove();
      void this.anim(p.face, [{ opacity: 0.2 }, { opacity: 1 }], 240);
    } else this.setFace(id, merged);
    await this.glowOutline();
  }
  async lift(id: PieceId, on: boolean) {
    const p = this.pieces[id], P = this.sockPose(id);
    p.g.classList.toggle("is-lift", on);
    await this.move(id, on ? { ...P, y: P.y - 14, r: 3, s: 1.04 } : P, on ? 240 : 300, { over: !on });
  }
  /** piece leaves the circle back toward a screen point (the carousel) */
  async flyOut(id: PieceId, to: DOMRect | null) {
    const p = this.pieces[id];
    if (to && !reduced()) {
      const [bx, by] = this.toBoard(to.x + to.width / 2, to.y + to.height / 2), s = Math.min(1.4, to.width / (CELLS[id].w * this.boardScale()));
      await Promise.all([this.move(id, { x: bx, y: by, r: 0, s }, 620, { arc: -40, ease: "cubic-bezier(.5,0,.3,1)" }), this.anim(p.g, [{ opacity: 1 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], 620)]);
    }
    p.g.classList.remove("is-lift"); this.hide(id);
  }
  async glow(id: PieceId) {
    if (reduced()) return;
    const s = this.pieces[id].seam, L = s.getTotalLength();
    s.style.strokeDasharray = `${L}`;
    s.animate([{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 1, offset: 0.55 }, { opacity: 0 }], { duration: 1000, fill: "forwards" });
    await this.anim(s, [{ strokeDashoffset: L }, { strokeDashoffset: 0 }], 380, "ease-out");
  }
  async glowOutline() {
    if (reduced()) { this.outLine.style.opacity = "1"; await new Promise((r) => setTimeout(r, 400)); this.outLine.style.opacity = "0"; return; }
    const C = 2 * Math.PI * (R1 + GAP + 5);
    this.outLine.style.strokeDasharray = `${f(C)} ${f(C)}`;
    await Promise.all([
      this.anim(this.outLine, [{ strokeDashoffset: C, opacity: 1 }, { strokeDashoffset: 0, opacity: 1, offset: 0.55 }, { strokeDashoffset: 0, opacity: 0 }], 1700, "ease-out"),
      this.anim(this.outHalo, [{ opacity: 0 }, { opacity: 0.95, offset: 0.5 }, { opacity: 0 }], 1700, "ease-in-out"),
    ]);
    this.outLine.style.opacity = "0"; this.outHalo.style.opacity = "0";
  }
  setWarn(id: PieceId, text: string | null) {
    const p = this.pieces[id];
    if (p.warn) { p.warn.remove(); p.warn = null; }
    if (!text) return;
    const [qx, qy] = CELLS[id].c, g = el("g", { class: "m4-warn" }, p.bob);
    el("circle", { cx: f(qx), cy: f(qy - 46 * FS), r: 12 * FS, fill: "#b4553a", stroke: "#fff6ea", "stroke-width": 2 }, g);
    txt(g, qx, qy - 41 * FS, "!", "m4-t-bang", 15 * FS, "middle", 700);
    el("title", {}, g).textContent = text;
    p.warn = g;
  }

  /** finale part 1: settle, close the air gaps, dissolve seams into one muted picture */
  async assemble() {
    const settle = (b: SVGGElement) => {
      const m = getComputedStyle(b).transform; b.classList.add("is-still"); b.style.transform = "";
      return m && m !== "none" ? this.anim(b, [{ transform: m }, { transform: "none" }], 420, "ease-out") : Promise.resolve();
    };
    await Promise.all([...RING.map((id) => settle(this.pieces[id].bob)), settle(this.coreBob)]);
    await Promise.all(RING.map((id) => this.move(id, this.sockPose(id, 0), 700, { ease: "cubic-bezier(.3,.7,.2,1)" })));
    await Promise.all([
      this.anim(this.coreCont, [{ opacity: 0 }, { opacity: 1 }], 600, "ease-out"), this.anim(this.coreBev, [{ opacity: 1 }, { opacity: 0 }], 600),
      ...RING.map((id, i) => this.anim(this.pieces[id].cont, [{ opacity: 0 }, { opacity: 1 }], 600, "ease-out", reduced() ? 0 : i * 60)),
      ...RING.map((id, i) => this.anim(this.pieces[id].bevel, [{ opacity: 1 }, { opacity: 0 }], 600, "ease", reduced() ? 0 : i * 60)),
    ]);
  }
}
