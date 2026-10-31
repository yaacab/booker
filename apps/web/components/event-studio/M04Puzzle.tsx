"use client";
/* M04 · «Моё событие» — round jigsaw assembled from a carousel.
   Data, draft storage, catalogue and submission are the existing Event Studio ones (EventStudioShell).
   Nothing here invents prices, availability or a booking: those come from the API or are labelled. */
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { EventStudioMapProps } from "./EventStudioMap";
import type { TalentItem, VenueItem } from "./types";
import { toVisual, fromVisual, type VisualDraft } from "./v5Adapter";
import { M04Engine, RING, PIECE_LABEL, FINALE_IMAGE, type Face, type PieceId } from "./m04Engine";
import { PILOT_CITIES } from "@/lib/copy";
import { apiBase } from "@/lib/api";
import "./m04-puzzle.css";

type V = VisualDraft & { hall?: string | null };
export type M04Submitted = { eventId: string; reused: boolean } | null;
type Props = EventStudioMapProps & { submitted: M04Submitted; onGoEvent: () => void; onGoHome: () => void };

const ph = (id: string, w = 700) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=72`;
const FORMATS = [
  { id: "private", title: "Частная вечеринка", note: "Друзья, музыка, свой ритм", img: ph("1470337458703-46ad1756a187") },
  { id: "wedding", title: "Свадьба", note: "Церемония и банкет", img: ph("1519167758481-83f550bb49b3") },
  { id: "corporate", title: "Корпоратив", note: "Команда и партнёры", img: ph("1492684223066-81342ee5ff30") },
  { id: "birthday", title: "День рождения", note: "Праздник с характером", img: ph("1528495612343-9ca9f4a4de28") },
  { id: "concert", title: "Концерт", note: "Сцена и зрители", img: ph("1470229722913-7c0e2dbbafd3") },
  { id: "other", title: "Другое", note: "Опишите свою идею", img: ph("1464366400600-7168b8af9bc3") },
];
const GUESTS = [30, 50, 80, 100, 150, 200, 300];
const BUDGETS = [10000, 25000, 50000, 100000, 150000, 200000, 300000, 500000];
const RIDER = ["Звук", "Свет", "Сцена", "Гримёрка", "Техника", "Трансфер"];
const TIMES = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);
const CITIES: string[] = [...PILOT_CITIES]; // same list as the catalogue (pilot: Moscow only)
const HASH: Record<PieceId, string> = { format: "eventFormat", date: "eventDate", guests: "eventGuests", artist: "artistDiscovery", venue: "venueDiscovery", rider: "rider", budget: "budget" };
const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const WD = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const rub = (n: number) => `${new Intl.NumberFormat("ru-RU").format(n)} ₽`;
const short = (n: number) => (n >= 1000 && n % 1000 === 0 ? `${n / 1000} тыс ₽` : rub(n)); // never round a real limit
const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

function moscowDays(n: number) {
  const now = new Date(Date.now() + 3 * 3600e3);
  const out: { iso: string; d: number; m: number; wd: number }[] = [];
  for (let i = 0; i < n; i++) {
    const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + i));
    out.push({ iso: t.toISOString().slice(0, 10), d: t.getUTCDate(), m: t.getUTCMonth(), wd: t.getUTCDay() });
  }
  return out;
}
const isFilled = (v: V, id: PieceId) =>
  id === "format" ? !!v.format : id === "date" ? !!v.dateISO && !!v.time && !!v.city : id === "guests" ? v.guests !== null
    : id === "artist" ? v.artists.length > 0 || !!v.artistsDeferred : id === "venue" ? !!v.venue || !!v.venueDeferred
      : id === "rider" ? !!v.rider : v.budget !== null;

type Opt = { key: string; title: string; sub?: string; img?: string; kind?: "defer" | "skeleton" | "error" | "empty"; talent?: TalentItem; venue?: VenueItem; value?: string | number };

export default function M04Puzzle(p: Props) {
  const v = useMemo<V>(() => toVisual(p.draft) as V, [p.draft]);
  const vRef = useRef(v); vRef.current = v;
  const days = useMemo(() => moscowDays(366), []);
  const minISO = days[1].iso, maxISO = days[365].iso; // today cannot be booked
  const filledCount = RING.filter((id) => isFilled(v, id)).length;
  const allFilled = filledCount === 7;

  const svgRef = useRef<SVGSVGElement>(null), eng = useRef<M04Engine | null>(null), busy = useRef(new Set<PieceId>());
  const cardRefs = useRef(new Map<string, HTMLButtonElement>()), detailPhoto = useRef<HTMLDivElement>(null);
  const [sec, setSec] = useState<PieceId>(() => RING.find((id) => !isFilled(toVisual(p.draft) as V, id)) ?? "format");
  const [idx, setIdx] = useState<Record<PieceId, number>>({ format: 0, date: 0, guests: 2, artist: 0, venue: 0, rider: 0, budget: 2 });
  const [detail, setDetail] = useState<{ kind: "artist" | "venue"; id: string } | null>(null);
  const [hallIdx, setHallIdx] = useState(0);
  const [editing, setEditing] = useState<PieceId | null>(null);
  const [time, setTime] = useState(v.time || "19:00"), [city, setCity] = useState(v.city || "Москва");
  const [ownGuests, setOwnGuests] = useState(""), [ownBudget, setOwnBudget] = useState("");
  const [riderSel, setRiderSel] = useState<string[]>(v.rider?.requirements ?? []), [riderNotes, setRiderNotes] = useState(v.rider?.notes ?? "");
  const riderRef = useRef(riderSel); riderRef.current = riderSel;
  const [dateDraft, setDateDraft] = useState("");
  const dateRef = useRef<HTMLInputElement>(null);
  const [dateStale, setDateStale] = useState(false);
  const [say, setSay] = useState("");
  const [fin, setFin] = useState<"none" | "run" | "title" | "buttons">("none");
  const finRef = useRef<HTMLDivElement>(null), finMuted = useRef<HTMLDivElement>(null), finVivid = useRef<HTMLDivElement>(null), finGlow = useRef<HTMLDivElement>(null);

  const update = useCallback((patch: Partial<V>) => { p.onDraftChange(fromVisual(p.draft, { ...vRef.current, ...patch } as VisualDraft)); }, [p]);

  /* ---------- faces from real data ---------- */
  const [known, setKnown] = useState<{ artists: Record<string, string>; venues: Record<string, { name: string; halls: { id: string; name: string; capacity: number | null }[] }> }>({ artists: {}, venues: {} });
  const talentById = useCallback((id: string) => p.talents.find((t) => t.id === id), [p.talents]);
  const venueById = useCallback((id: string | null) => {
    if (!id) return undefined;
    const fromSearch = p.venues.find((x) => x.id === id);
    if (fromSearch) return fromSearch;
    const k = known.venues[id];
    return k ? ({ id, name: k.name, city: "", honorariumFrom: null, halls: k.halls } as VenueItem) : undefined;
  }, [p.venues, known.venues]);
  const faceFor = useCallback((id: PieceId, x: V): Face => {
    switch (id) {
      case "format": { const fm = FORMATS.find((q) => q.id === x.format) ?? FORMATS[5]; return { kind: "photo", img: fm.img, value: fm.title }; }
      case "date": { const d = x.dateISO ? new Date(`${x.dateISO}T12:00:00Z`) : null; return { kind: "text", text: d ? `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}` : "—", sub: `${x.time ?? ""} · ${x.city ?? ""}` }; }
      case "guests": return { kind: "text", text: String(x.guests ?? "—"), sub: "гостей" };
      case "artist": {
        if (x.artistsDeferred || !x.artists.length) return { kind: "text", text: "Позже", sub: "подберём варианты" };
        const ts = x.artists.map((a) => talentById(a)), names = ts.map((t, i) => t?.name ?? known.artists[x.artists[i]] ?? `Артист ${i + 1}`);
        if (ts.length > 1) return { kind: "collage", imgs: ts.map((t) => t?.mediaUrl || FORMATS[4].img), value: names.join(" + ") };
        return ts[0]?.mediaUrl ? { kind: "photo", img: ts[0].mediaUrl, value: names[0] } : { kind: "text", text: names[0].split(" ")[0], sub: ts[0]?.roleLabel ?? "артист" };
      }
      case "venue": {
        if (x.venueDeferred || !x.venue) return { kind: "text", text: "Позже", sub: "подберём варианты" };
        const vn = venueById(x.venue), name = vn?.name ?? "Площадка", val = x.hall ? `${name} · ${x.hall}` : name;
        return vn?.mediaUrl ? { kind: "photo", img: vn.mediaUrl, value: val } : { kind: "text", text: name.length > 12 ? name.slice(0, 11) + "…" : name, sub: x.hall ?? "площадка" };
      }
      case "rider": { const n = x.rider?.requirements?.length ?? 0; return { kind: "text", text: n ? String(n) : "Без", sub: n ? "требований" : "особых требований" }; }
      case "budget": return { kind: "text", text: x.budget ? (x.budget % 1000 === 0 ? `${x.budget / 1000} тыс` : new Intl.NumberFormat("ru-RU").format(x.budget)) : "—", sub: "₽ · лимит" };
    }
  }, [talentById, venueById, known.artists]);

  /* ---------- engine lifecycle ---------- */
  useEffect(() => {
    if (!svgRef.current) return;
    const e = new M04Engine(svgRef.current, "m4");
    eng.current = e;
    for (const id of RING) if (isFilled(vRef.current, id)) e.show(id, faceFor(id, vRef.current));
    return () => { eng.current = null; while (svgRef.current?.firstChild) svgRef.current.removeChild(svgRef.current.firstChild); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // keep faces/visibility in sync with the draft (other tab, restored draft, catalogue arrival)
  useEffect(() => {
    const e = eng.current; if (!e || fin !== "none") return;
    for (const id of RING) {
      if (busy.current.has(id)) continue;
      const on = isFilled(v, id), shown = e.pieces[id].filled;
      if (on) e.show(id, faceFor(id, v)); else if (shown) e.hide(id);
    }
  }, [v, faceFor, fin]);
  // honest warnings: hall too small, date changed after suppliers were chosen
  useEffect(() => {
    const e = eng.current; if (!e) return;
    const vn = venueById(v.venue), hall = vn?.halls?.find((h) => h.name === v.hall);
    const small = hall?.capacity && v.guests && v.guests > hall.capacity ? `зал на ${hall.capacity} — гостей ${v.guests}` : null;
    e.setWarn("venue", small ?? (dateStale && v.venue ? "проверить на новую дату" : null));
    e.setWarn("artist", dateStale && v.artists.length ? "проверить на новую дату" : null);
  }, [v, venueById, dateStale]);
  useEffect(() => { if (eng.current) eng.current.onPiece = (id) => void editPiece(id); });

  // artists kept in an old draft or a stale ?artist= link may no longer be public (removed or hidden profiles): drop them quietly
  const checkedArtists = useRef(new Set<string>());
  const artistKey = v.artists.join(",");
  useEffect(() => {
    const ids = v.artists.filter((id) => !checkedArtists.current.has(id));
    if (!ids.length) return;
    ids.forEach((id) => checkedArtists.current.add(id));
    void Promise.all(ids.map((id) => fetch(`${apiBase()}/artists/${encodeURIComponent(id)}`, { cache: "no-store" })
      .then(async (r) => {
        if (r.status === 404) return id;
        if (r.ok) { const a = await r.json(); if (a?.name) setKnown((k) => ({ ...k, artists: { ...k.artists, [id]: a.name } })); }
        return null;
      }).catch(() => null)))
      .then((gone) => {
        const drop = gone.filter((x): x is string => !!x);
        if (!drop.length) return;
        const rest = vRef.current.artists.filter((a) => !drop.includes(a));
        update({ artists: rest } as Partial<V>);
        announce(drop.length === 1 ? "Артист из черновика больше недоступен — выберите другого" : "Артисты из черновика больше недоступны — выберите других");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artistKey]);

  const checkedVenues = useRef(new Set<string>());
  useEffect(() => {
    const id = v.venue;
    if (!id || checkedVenues.current.has(id)) return;
    checkedVenues.current.add(id);
    void fetch(`${apiBase()}/venues/${encodeURIComponent(id)}`, { cache: "no-store" }).then(async (r) => {
      if (r.status === 404) {
        if (vRef.current.venue === id) { update({ venue: null, hall: null } as Partial<V>); announce("Площадка из черновика больше недоступна — выберите другую"); }
        return;
      }
      if (!r.ok) return;
      const data = await r.json();
      const halls = ((data?.halls ?? []) as { id?: string; name?: string; capacity?: number | null }[])
        .filter((h) => h.id && h.name).map((h) => ({ id: h.id!, name: h.name!, capacity: h.capacity ?? null }));
      setKnown((k) => ({ ...k, venues: { ...k.venues, [id]: { name: data?.name ?? "Площадка", halls } } }));
      if (vRef.current.venue !== id) return;
      const wanted = pendingHall.current ? halls.find((h) => h.id === pendingHall.current) : halls.length === 1 ? halls[0] : undefined;
      pendingHall.current = null;
      if (wanted && vRef.current.hall !== wanted.name) update({ hall: wanted.name } as Partial<V>);
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v.venue]);

  /* ---------- history: Back closes one layer ---------- */
  useEffect(() => {
    const fromHash = RING.find((id) => `#${HASH[id]}` === window.location.hash);
    if (fromHash) setSec(fromHash);
    const onPop = (ev: PopStateEvent) => {
      if (detailOpen.current) { setDetail(null); return; }
      const id = (ev.state?.m4sec as PieceId) || RING.find((x) => `#${HASH[x]}` === window.location.hash);
      if (id) setSec(id);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const detailOpen = useRef(false); detailOpen.current = !!detail;
  const pendingHall = useRef<string | null>(null);
  // a restored draft goes through the same rules as the controls: past/today dates and unknown cities are reset
  useEffect(() => {
    const x = vRef.current, patch: Partial<V> = {};
    const badDate = !!x.dateISO && (x.dateISO < minISO || x.dateISO > maxISO);
    const badCity = !!x.city && !CITIES.includes(x.city);
    if (badDate || badCity) Object.assign(patch, { dateISO: null, date: null });
    if (badCity) { Object.assign(patch, { city: CITIES[0] }); setCity(CITIES[0]); }
    if (x.time && !TIMES.includes(x.time)) { Object.assign(patch, { time: "19:00" }); setTime("19:00"); }
    // «Запросить дату» from the catalogue or a profile: /events/new?artist=<id> puts that artist into the line-up
    const url = new URL(window.location.href), preset = url.searchParams.get("artist");
    const presetVenue = url.searchParams.get("venue"), presetHall = url.searchParams.get("hall");
    if (preset && !x.artists.includes(preset)) Object.assign(patch, { artists: [preset, ...x.artists].slice(0, 3), artistsDeferred: false });
    if (presetVenue && !["need", "own", "unknown"].includes(presetVenue)) {
      if (presetVenue !== x.venue) Object.assign(patch, { venue: presetVenue, venueDeferred: false, hall: null });
      pendingHall.current = presetHall;
    }
    if (preset || presetVenue || presetHall || url.searchParams.has("roof")) {
      for (const k of ["artist", "venue", "hall", "roof"]) url.searchParams.delete(k);
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    }
    if (Object.keys(patch).length) {
      update(patch);
      if (badDate || badCity) { announce("Дата в черновике больше недоступна — выберите новую"); setSec("date"); window.history.replaceState({ m4sec: "date" }, "", `#${HASH.date}`); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const goSec = useCallback((id: PieceId, push = true) => {
    setSec(id);
    if (push && typeof window !== "undefined") window.history.pushState({ m4sec: id }, "", `#${HASH[id]}`);
  }, []);

  /* ---------- carousel options ---------- */
  const opts: Opt[] = useMemo(() => {
    switch (sec) {
      case "format": return FORMATS.map((f) => ({ key: f.id, title: f.title, sub: f.note, img: f.img }));
      case "date": return []; // native date picker in the controls row
      case "guests": return GUESTS.map((n) => ({ key: String(n), title: n >= 300 ? "300+" : String(n), sub: "гостей", value: n }));
      case "budget": return BUDGETS.map((n) => ({ key: String(n), title: short(n), sub: "лимит · не цена", value: n }));
      case "rider": return RIDER.map((r) => ({ key: r, title: r, sub: riderSel.includes(r) ? "выбрано" : "нажмите, чтобы отметить" }));
      case "artist": case "venue": {
        if (p.loadingTalents) return [0, 1, 2, 3].map((i) => ({ key: `sk${i}`, title: "", kind: "skeleton" as const }));
        if (p.talentsError) return [{ key: "err", title: "Каталог временно недоступен", sub: "черновик сохранён", kind: "error" as const }];
        const list: Opt[] = sec === "artist"
          ? p.talents.map((t) => ({ key: t.id, title: t.name, sub: t.roleLabel, img: t.mediaUrl, talent: t }))
          : p.venues.map((x) => ({ key: x.id, title: x.name, sub: x.metro || x.district || x.city, img: x.mediaUrl, venue: x }));
        if (!list.length) {
          list.push(
            sec === "artist"
              ? { key: "empty", title: "Пока нет доступных артистов", sub: "в публичном каталоге нет профилей · не из‑за даты", kind: "empty" }
              : { key: "empty", title: "Площадки пока не в витрине", sub: "публичный каталог площадок отключён · можно позже", kind: "empty" },
          );
        }
        list.push({ key: "defer", title: "Подобрать позже", sub: "предложим варианты", kind: "defer" });
        return list;
      }
    }
  }, [sec, days, riderSel, p.loadingTalents, p.talentsError, p.talents, p.venues]);
  const cur = Math.max(0, Math.min(idx[sec] ?? 0, opts.length - 1));
  const setCur = useCallback((n: number) => setIdx((s) => ({ ...s, [sec]: Math.max(0, Math.min(n, opts.length - 1)) })), [sec, opts.length]);
  // centre the current value when a parameter opens
  useEffect(() => {
    const x = vRef.current; let n = -1;
    if (sec === "format") n = FORMATS.findIndex((f) => f.id === x.format);
    if (sec === "date") n = days.findIndex((d) => d.iso === x.dateISO);
    if (sec === "guests") n = GUESTS.indexOf(x.guests ?? -1);
    if (sec === "budget") n = BUDGETS.indexOf(x.budget ?? -1);
    if (sec === "artist" && x.artists[0]) n = opts.findIndex((o) => o.key === x.artists[0]);
    if (sec === "venue" && x.venue) n = opts.findIndex((o) => o.key === x.venue);
    if (n >= 0) setIdx((s) => ({ ...s, [sec]: n }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sec]);

  const rectOf = (key: string) => cardRefs.current.get(key)?.getBoundingClientRect() ?? null;
  const announce = (s: string) => setSay(s);

  /* ---------- choosing ---------- */
  const afterFill = useCallback(async (id: PieceId, wasFilled: boolean, next: V) => {
    setEditing(null);
    if (!wasFilled) {
      const nxt = RING.find((x) => !isFilled(next, x));
      if (nxt) { await sleep(160); goSec(nxt); }
    }
  }, [goSec]);
  const commit = useCallback(async (id: PieceId, patch: Partial<V>, from: DOMRect | null, advance = true) => {
    const e = eng.current, wasFilled = isFilled(vRef.current, id), next = { ...vRef.current, ...patch } as V;
    busy.current.add(id);
    update(patch);
    announce(`${PIECE_LABEL[id]}: выбрано. ${RING.filter((x) => isFilled(next, x)).length} из 7`);
    try { if (e) await e.flyIn(id, faceFor(id, next), from); } finally { busy.current.delete(id); }
    if (advance) await afterFill(id, wasFilled, next); else setEditing(null);
  }, [update, faceFor, afterFill]);

  // rider items count as soon as they are ticked; «Готово» only moves on
  const riderOf = (sel: string[], notes: string) => (sel.length || notes.trim() ? { matches: 0, open: sel.length, requirements: [...sel], notes: notes.trim() } : null);
  const toggleRider = useCallback(async (key: string, from: DOMRect | null) => {
    const sel = riderRef.current.includes(key) ? riderRef.current.filter((x) => x !== key) : [...riderRef.current, key];
    riderRef.current = sel; setRiderSel(sel);
    const rider = riderOf(sel, riderNotes);
    if (!rider) {
      if (isFilled(vRef.current, "rider")) { busy.current.add("rider"); update({ rider: null } as Partial<V>); try { await eng.current?.flyOut("rider", null); } finally { busy.current.delete("rider"); } }
      announce("Райдер пуст"); return;
    }
    if (!isFilled(vRef.current, "rider")) return commit("rider", { rider }, from, false);
    update({ rider }); eng.current?.setFace("rider", faceFor("rider", { ...vRef.current, rider }));
    announce(`Райдер: ${sel.length} ${sel.length === 1 ? "пункт" : "пункта"}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riderNotes, commit, update, faceFor]);
  const riderDone = useCallback(async () => {
    const rider = riderOf(riderRef.current, riderNotes);
    if (rider && !isFilled(vRef.current, "rider")) return commit("rider", { rider }, null);
    if (rider) update({ rider });
    const nxt = RING.find((x) => x !== "rider" && !isFilled(vRef.current, x));
    if (nxt) goSec(nxt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riderNotes, commit, update, goSec]);
  const chooseDate = useCallback(async () => {
    const iso = dateDraft || minISO;
    if (iso < minISO || iso > maxISO) return;
    if (vRef.current.dateISO && vRef.current.dateISO !== iso && (vRef.current.artists.length || vRef.current.venue)) setDateStale(true);
    return commit("date", { dateISO: iso, date: Number(iso.slice(-2)), time, city }, dateRef.current?.getBoundingClientRect() ?? null);
  }, [dateDraft, minISO, maxISO, time, city, commit]);

  const activate = useCallback(async (o: Opt) => {
    if (o.kind === "skeleton" || o.kind === "empty") return;
    if (o.kind === "error") { p.onReloadCatalog?.(); return; }
    const from = rectOf(o.key);
    switch (sec) {
      case "format": return commit("format", { format: o.key }, from);
      case "date": {
        if (vRef.current.dateISO && vRef.current.dateISO !== o.value && (vRef.current.artists.length || vRef.current.venue)) setDateStale(true);
        return commit("date", { dateISO: String(o.value), date: Number(String(o.value).slice(-2)), time, city }, from);
      }
      case "guests": return commit("guests", { guests: Number(o.value) }, from);
      case "budget": return commit("budget", { budget: Number(o.value) }, from);
      case "rider": return toggleRider(o.key, from);
      case "artist":
        if (o.kind === "defer") return commit("artist", { artists: [], artistsDeferred: true }, from);
        setDetail({ kind: "artist", id: o.key }); window.history.pushState({ m4detail: 1 }, "", window.location.hash); return;
      case "venue":
        if (o.kind === "defer") return commit("venue", { venue: null, venueDeferred: true, hall: null }, from);
        setHallIdx(0); setDetail({ kind: "venue", id: o.key }); window.history.pushState({ m4detail: 1 }, "", window.location.hash); return;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sec, commit, time, city, p.onReloadCatalog, toggleRider]);

  const closeDetail = useCallback(() => { if (detailOpen.current) window.history.back(); }, []);
  const chooseDetail = useCallback(async () => {
    if (!detail) return;
    const from = detailPhoto.current?.getBoundingClientRect() ?? null, x = vRef.current;
    setDetail(null); window.history.back();
    if (detail.kind === "venue") {
      const vn = venueById(detail.id), hall = vn?.halls?.[hallIdx]?.name ?? null;
      setDateStale(false);
      return commit("venue", { venue: detail.id, venueDeferred: false, hall }, from);
    }
    const inList = x.artists.includes(detail.id);
    if (inList) { // remove from the line-up
      const rest = x.artists.filter((a) => a !== detail.id);
      if (!rest.length) { busy.current.add("artist"); update({ artists: [] }); await eng.current?.flyOut("artist", null); busy.current.delete("artist"); announce("Артист убран"); return; }
      update({ artists: rest }); eng.current?.setFace("artist", faceFor("artist", { ...x, artists: rest })); announce("Артист убран из состава"); return;
    }
    if (x.artists.length && !x.artistsDeferred && x.artists.length < 3) { // add to the line-up: merge + gold outline
      const next = { ...x, artists: [...x.artists, detail.id] };
      busy.current.add("artist"); update({ artists: next.artists });
      announce(`Артист добавлен в состав · ${next.artists.length} из 3`);
      try { await eng.current?.mergeIn("artist", faceFor("artist", { ...x, artists: [detail.id] }), faceFor("artist", next), from); } finally { busy.current.delete("artist"); }
      return;
    }
    setDateStale(false);
    return commit("artist", { artists: [detail.id], artistsDeferred: false }, from);
  }, [detail, hallIdx, venueById, commit, update, faceFor]);

  const editPiece = useCallback(async (id: PieceId) => {
    if (editing && editing !== id) await eng.current?.lift(editing, false);
    setEditing(id); goSec(id); await eng.current?.lift(id, true);
  }, [editing, goSec]);
  const cancelEdit = useCallback(async () => { if (!editing) return; const id = editing; setEditing(null); await eng.current?.lift(id, false); }, [editing]);
  const clearPiece = useCallback(async () => {
    if (!editing) return;
    const id = editing, center = opts[cur] ? rectOf(opts[cur].key) : null;
    const patch: Partial<V> = id === "format" ? { format: null } : id === "date" ? { dateISO: null, date: null } : id === "guests" ? { guests: null }
      : id === "artist" ? { artists: [], artistsDeferred: false } : id === "venue" ? { venue: null, venueDeferred: false, hall: null } : id === "rider" ? { rider: null } : { budget: null };
    busy.current.add(id); setEditing(null); update(patch);
    await eng.current?.flyOut(id, center); busy.current.delete(id);
    announce(`${PIECE_LABEL[id]}: убрано`);
  }, [editing, opts, cur, update]);
  useEffect(() => { // leaving the edited parameter without a new choice keeps the old one
    if (editing && editing !== sec) void cancelEdit();
  }, [sec, editing, cancelEdit]);

  /* ---------- keyboard / swipe / wheel ---------- */
  const onKey = (e: ReactKeyboardEvent) => {
    if (e.key === "ArrowRight") { e.preventDefault(); setCur(cur + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setCur(cur - 1); }
    if (e.key === "Enter" && opts[cur] && (e.target as HTMLElement).tagName !== "BUTTON") { e.preventDefault(); void activate(opts[cur]); }
    if (e.key === "Escape") void cancelEdit();
  };
  const swipe = useRef<{ x: number; t: number } | null>(null);
  const onDown = (e: ReactPointerEvent) => { swipe.current = { x: e.clientX, t: Date.now() }; };
  const onUp = (e: ReactPointerEvent) => { const s = swipe.current; swipe.current = null; if (!s) return; const dx = e.clientX - s.x; if (Math.abs(dx) > 40) setCur(cur + (dx < 0 ? 1 : -1)); };
  const wheelT = useRef(0);
  const onWheel = (e: React.WheelEvent) => { const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY; if (Math.abs(d) < 12 || Date.now() - wheelT.current < 260) return; wheelT.current = Date.now(); setCur(cur + (d > 0 ? 1 : -1)); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { if (detailOpen.current) closeDetail(); else void cancelEdit(); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [closeDetail, cancelEdit]);

  /* ---------- finale after a confirmed submission ---------- */
  useEffect(() => {
    if (!p.submitted || fin !== "none") return;
    let alive = true;
    (async () => {
      setFin("run");
      const e = eng.current;
      if (e) await e.assemble();
      const box = e?.screenRectOfBoard(), c = e?.centerScreen(), F = finRef.current;
      if (F && box && c) {
        for (const L of [finMuted.current, finVivid.current]) if (L) Object.assign(L.style, { left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px` });
        const W = window.innerWidth, H = window.innerHeight, at = (r: number) => `circle(${r}px at ${c.x}px ${c.y}px)`;
        F.style.clipPath = at(c.r); F.style.opacity = "1";
        if (finGlow.current) Object.assign(finGlow.current.style, { left: `${c.x}px`, top: `${c.y}px`, width: `${c.r * 2.4}px`, height: `${c.r * 2.4}px` });
        if (!reduced()) {
          await Promise.all([
            finVivid.current!.animate([{ clipPath: `circle(0px at ${c.x - box.x}px ${c.y - box.y}px)` }, { clipPath: `circle(${c.r * 1.25}px at ${c.x - box.x}px ${c.y - box.y}px)` }], { duration: 1300, easing: "cubic-bezier(.25,.6,.2,1)", fill: "forwards" }).finished,
            finGlow.current!.animate([{ transform: "translate(-50%,-50%) scale(.01)", opacity: 0.85 }, { transform: "translate(-50%,-50%) scale(1)", opacity: 0 }], { duration: 1100, easing: "ease-out", fill: "forwards" }).finished,
          ]);
          finVivid.current!.getAnimations().forEach((a) => a.cancel()); finVivid.current!.style.clipPath = "none";
          const Rc = Math.max(...[[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => Math.hypot(x - c.x, y - c.y))) + 4;
          const sc = Math.max(W / box.w, H / box.h) * 1.04, tx = W / 2 - (box.x + box.w / 2), ty = H / 2 - (box.y + box.h / 2);
          const grow = [{ transform: "translate(0px,0px) scale(1)" }, { transform: `translate(${tx}px,${ty}px) scale(${sc})` }];
          await Promise.all([
            F.animate([{ clipPath: at(c.r) }, { clipPath: at(Rc) }], { duration: 1150, easing: "cubic-bezier(.65,0,.25,1)", fill: "forwards" }).finished,
            finMuted.current!.animate(grow, { duration: 1150, easing: "cubic-bezier(.65,0,.25,1)", fill: "forwards" }).finished,
            finVivid.current!.animate(grow, { duration: 1150, easing: "cubic-bezier(.65,0,.25,1)", fill: "forwards" }).finished,
          ]);
        } else { finVivid.current!.style.clipPath = "none"; F.style.clipPath = "none"; }
      }
      if (!alive) return;
      setFin("title"); announce(p.submitted?.reused ? "Заявка уже отправлена" : "Заявка отправлена");
      await sleep(1500);
      if (alive) setFin("buttons");
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.submitted]);

  /* ---------- derived view ---------- */
  const saveText = { saving: "сохраняем…", saved: "сохранено на этом устройстве", error: "не сохраняется на этом устройстве", offline: "нет сети · изменения на устройстве", conflict: "черновик изменён в другой вкладке" }[p.saveStatus];
  const coreTitle = FORMATS.find((f) => f.id === v.format)?.title ?? "Новое событие";
  const summary = [v.artists.length ? v.artists.map((a) => talentById(a)?.name ?? known.artists[a] ?? "артист").join(" + ") : v.artistsDeferred ? "артиста подберём" : null,
    v.venue ? `${venueById(v.venue)?.name ?? "площадка"}${v.hall ? ` · ${v.hall}` : ""}` : v.venueDeferred ? "площадку подберём" : null].filter(Boolean).join(" · ");
  const warnText = (() => { const vn = venueById(v.venue), hall = vn?.halls?.find((h) => h.name === v.hall); if (hall?.capacity && v.guests && v.guests > hall.capacity) return `зал на ${hall.capacity} — гостей ${v.guests}`; return dateStale && (v.artists.length || v.venue) ? "дата изменилась — проверим артиста и зал" : null; })();
  const coreMode = p.submitting ? "sending" : allFilled && !editing ? "ready" : "build";
  const carouselHidden = (allFilled && !editing) || fin !== "none";
  const dTalent = detail?.kind === "artist" ? talentById(detail.id) : undefined, dVenue = detail?.kind === "venue" ? venueById(detail.id) : undefined;
  const ringC = 2 * Math.PI * 41;

  return (
    <div id="m4" className={`m4-root${fin !== "none" ? " is-finale" : ""}${coreMode === "ready" || coreMode === "sending" || fin !== "none" ? " is-ready" : ""}`}>
      <Backdrop />
      <header className="m4-bar">
        <a href="/" className="m4-logo">Букер</a>
        <span className={`m4-save is-${p.saveStatus}`} aria-live="polite">{saveText}{p.saveStatus === "error" && p.onRetrySave ? <button type="button" onClick={p.onRetrySave}>повторить</button> : null}</span>
      </header>

      <main className="m4-main">
        <div className="m4-puzzle">
          <svg ref={svgRef} className="m4-svg" aria-label="Пазл события: семь частей вокруг центра" role="group" />
          <div className={`m4-core is-${coreMode}`}>
            <svg className="m4-core-ring" viewBox="0 0 100 100" aria-hidden><circle cx="50" cy="50" r="41" className="m4-ring-bg" /><circle cx="50" cy="50" r="41" className="m4-ring-fg" style={{ strokeDasharray: coreMode === "sending" ? `${ringC * 0.18} ${ringC}` : `${(ringC * filledCount) / 7} ${ringC}` }} /></svg>
            <span className="m4-k">Моё событие</span>
            <b className="m4-core-t">{coreTitle}</b>
            {coreMode === "build" && <>{warnText ? <span className="m4-core-warn">проверьте: {warnText}</span> : <span className="m4-core-s">{summary || "выберите в карусели"}</span>}<span className="m4-core-n">{filledCount} из 7</span></>}
            {coreMode === "ready" && <><button type="button" className="m4-send" onClick={p.onContinue}>{p.submitError ? "Повторить" : <>Отправить<span className="m4-send-x">запрос</span></>}</button>{warnText ? <span className="m4-core-warn">проверьте: {warnText}</span> : <span className="m4-core-n">7 из 7 собрано</span>}</>}
            {coreMode === "sending" && <><span className="m4-core-s">Отправляем…</span><span className="m4-core-n">ждём ответ сервера</span></>}
          </div>
        </div>
        {p.submitError && fin === "none" && <p className="m4-error" role="alert">{p.submitError}</p>}

        <section className={`m4-pick${carouselHidden ? " is-hidden" : ""}`} aria-hidden={carouselHidden}>
          <nav className="m4-params" aria-label="Части события">
            {RING.map((id) => (
              <button key={id} type="button" className={`m4-param${id === sec ? " is-on" : ""}${isFilled(v, id) ? " is-done" : ""}`} aria-current={id === sec ? "step" : undefined} onClick={() => goSec(id)}>
                {isFilled(v, id) ? "✓ " : ""}{PIECE_LABEL[id]}{id === "artist" && v.artists.length > 1 ? ` · ${v.artists.length}` : ""}
              </button>
            ))}
          </nav>
          <div className="m4-sub">
            {sec === "date" && <>
              <label className="m4-own">Дата<input ref={dateRef} type="date" min={minISO} max={maxISO} value={dateDraft || (v.dateISO && v.dateISO >= minISO ? v.dateISO : minISO)} onChange={(e) => setDateDraft(e.target.value)} aria-label="Дата события" /></label>
              <label className="m4-own">Время<select className="m4-chip m4-select" value={time} aria-label="Время начала" onChange={(e) => { setTime(e.target.value); if (isFilled(v, "date")) update({ time: e.target.value }); }}>{TIMES.map((t) => <option key={t}>{t}</option>)}</select></label>
              <select className="m4-chip m4-select" value={city} aria-label="Город" onChange={(e) => { setCity(e.target.value); if (isFilled(v, "date")) update({ city: e.target.value }); }}>{(CITIES.includes(city) ? CITIES : [city, ...CITIES]).map((c) => <option key={c}>{c}</option>)}</select>
              <button type="button" className="m4-chip is-on" onClick={() => void chooseDate()}>{isFilled(v, "date") ? "Обновить дату" : "Выбрать"}</button>
            </>}
            {sec === "guests" && <label className="m4-own">Своё число<input inputMode="numeric" type="number" min={1} max={5000} value={ownGuests} onChange={(e) => setOwnGuests(e.target.value)} aria-describedby="m4-guests-hint" /><button type="button" className="m4-chip is-on" disabled={!(Number(ownGuests) >= 1 && Number(ownGuests) <= 5000)} onClick={() => commit("guests", { guests: Math.floor(Number(ownGuests)) }, null)}>Выбрать</button>{ownGuests !== "" && !(Number(ownGuests) >= 1 && Number(ownGuests) <= 5000) ? <span id="m4-guests-hint" className="m4-fine m4-invalid" role="alert">от 1 до 5 000 гостей</span> : null}</label>}
            {sec === "budget" && <label className="m4-own">Свой лимит, ₽<input inputMode="numeric" type="number" min={1000} step={1} value={ownBudget} onChange={(e) => setOwnBudget(e.target.value)} aria-describedby="m4-budget-hint" /><button type="button" className="m4-chip is-on" disabled={!(Number(ownBudget) >= 1000)} onClick={() => commit("budget", { budget: Math.floor(Number(ownBudget)) }, null)}>Выбрать</button>{ownBudget !== "" && !(Number(ownBudget) >= 1000) ? <span id="m4-budget-hint" className="m4-fine m4-invalid" role="alert">минимум 1 000 ₽</span> : <span id="m4-budget-hint" className="m4-fine">лимит, а не цена: цену считает сервер</span>}</label>}
            {sec === "rider" && <div className="m4-rider"><textarea rows={2} maxLength={2000} placeholder="Пожелания: время монтажа, доступ, оборудование" value={riderNotes} onChange={(e) => setRiderNotes(e.target.value)} onBlur={() => { const r = riderOf(riderRef.current, riderNotes); if (r && isFilled(vRef.current, "rider")) update({ rider: r }); }} aria-label="Пожелания к райдеру" /><button type="button" className="m4-chip is-on" onClick={() => void riderDone()}>Готово</button><span className="m4-fine">совместимость не проверена — подтвердят участники</span></div>}
            {(sec === "artist" || sec === "venue") && <span className="m4-fine">{sec === "artist" ? "до 3 артистов · выбор — ещё не бронь" : "площадка и конкретный зал · вместимость из каталога"}</span>}
            {editing === sec && <button type="button" className="m4-chip m4-clear" onClick={() => void clearPiece()}>Убрать из события</button>}
          </div>
          <div className="m4-car" role="listbox" aria-label={PIECE_LABEL[sec]} tabIndex={0} onKeyDown={onKey} onPointerDown={onDown} onPointerUp={onUp} onWheel={onWheel}>
            {opts.map((o, i) => {
              const d = i - cur, a = Math.abs(d);
              if (a > 3) return null;
              const sel = (sec === "format" && v.format === o.key) || (sec === "date" && v.dateISO === o.key) || (sec === "guests" && v.guests === o.value) || (sec === "budget" && v.budget === o.value)
                || (sec === "artist" && v.artists.includes(o.key)) || (sec === "venue" && v.venue === o.key) || (sec === "rider" && riderSel.includes(o.key))
                || (o.kind === "defer" && ((sec === "artist" && v.artistsDeferred) || (sec === "venue" && v.venueDeferred)));
              const style = { "--d": d, "--a": a } as CSSProperties;
              return (
                <button key={o.key} ref={(n) => { if (n) cardRefs.current.set(o.key, n); else cardRefs.current.delete(o.key); }} type="button" role="option" aria-selected={sel}
                  className={`m4-card${o.img ? " has-img" : ""}${o.kind ? ` is-${o.kind}` : ""}${a === 0 ? " is-center" : ""}${a === 3 ? " is-far" : ""}`} style={style} tabIndex={a === 0 ? 0 : -1}
                  onClick={() => { if (a !== 0) setCur(i); void activate(o); }}
                  onMouseEnter={() => a === 0 && eng.current?.hint(sec, !isFilled(v, sec))} onMouseLeave={() => eng.current?.hint(sec, false)}>
                  {o.img ? <span className="m4-card-img" style={{ backgroundImage: `url("${o.img}")` }} /> : null}
                  <span className="m4-card-k">{o.kind === "defer" ? PIECE_LABEL[sec] : sec === "date" ? o.sub : PIECE_LABEL[sec]}</span>
                  {o.kind === "defer" && <span className="m4-card-star" aria-hidden>✦</span>}
                  <span className="m4-card-t">{o.title}</span>
                  {sec !== "date" && o.sub && o.kind !== "skeleton" ? <span className="m4-card-s">{o.sub}</span> : null}
                  {o.talent && <span className="m4-card-s">{o.talent.availabilityLabel.replace(/^●\s*/, "")}{o.talent.honorariumFrom ? ` · от ${short(o.talent.honorariumFrom)}` : ""}</span>}
                  {o.venue?.honorariumFrom ? <span className="m4-card-s">от {short(o.venue.honorariumFrom)} · тариф каталога</span> : null}
                  {(sec === "artist" || sec === "venue") && !o.kind && !sel && <span className="m4-more">подробнее</span>}
                  {o.kind === "error" && <span className="m4-retry">Повторить</span>}
                  {sel && <span className="m4-tick" aria-hidden>✓</span>}
                </button>
              );
            })}
          </div>
          {sec !== "date" && <div className="m4-nav">
            <button type="button" className="m4-arrow" aria-label="Предыдущий вариант" onClick={() => setCur(cur - 1)} disabled={cur <= 0}>‹</button>
            <span className="m4-count" aria-hidden>{opts.length ? `${cur + 1} / ${opts.length}` : ""}</span>
            <button type="button" className="m4-arrow" aria-label="Следующий вариант" onClick={() => setCur(cur + 1)} disabled={cur >= opts.length - 1}>›</button>
          </div>}
          {p.legacyLink ? <div className="m4-legacy">{p.legacyLink}</div> : null}
        </section>
      </main>

      {detail && (dTalent || dVenue) && (
        <div className="m4-detail-wrap" onClick={(e) => { if (e.target === e.currentTarget) closeDetail(); }}>
          <div className="m4-detail" role="dialog" aria-modal="true" aria-label={dTalent?.name ?? dVenue?.name}>
            <div ref={detailPhoto} className="m4-detail-ph" style={{ backgroundImage: (dTalent?.mediaUrl || dVenue?.mediaUrl) ? `url("${dTalent?.mediaUrl || dVenue?.mediaUrl}")` : undefined }}>{!(dTalent?.mediaUrl || dVenue?.mediaUrl) && <span>{(dTalent?.name || dVenue?.name || "").slice(0, 1)}</span>}</div>
            <div className="m4-detail-tx">
              <span className="m4-k">{dTalent ? "Артист" : "Площадка"}</span>
              <h2>{dTalent?.name ?? dVenue?.name}</h2>
              <div className="m4-tags">{dTalent && <span>{dTalent.roleLabel}</span>}{dTalent?.verified && <span>проверен</span>}{dVenue?.metro && <span>м. {dVenue.metro}</span>}{dVenue?.district && <span>{dVenue.district}</span>}</div>
              <ul className="m4-facts">
                {dTalent && <li><b>Дата</b>{dTalent.availabilityLabel.replace(/^●\s*/, "")}</li>}
                {(dTalent?.honorariumFrom || dVenue?.honorariumFrom) ? <li><b>Тариф</b>от {rub((dTalent?.honorariumFrom || dVenue?.honorariumFrom) as number)} · из каталога, не итоговая цена</li> : <li><b>Тариф</b>по запросу</li>}
                {dVenue?.address && <li><b>Адрес</b>{dVenue.address}</li>}
                {dVenue?.availabilityLabel && <li><b>Календарь</b>{dVenue.availabilityLabel}</li>}
              </ul>
              {dVenue && (dVenue.halls?.length ? <div className="m4-halls"><span className="m4-k">Выберите зал</span><div>{dVenue.halls.map((h, i) => <button key={h.id} type="button" className={`m4-chip${i === hallIdx ? " is-on" : ""}`} aria-pressed={i === hallIdx} onClick={() => setHallIdx(i)}>{h.name}{h.capacity ? ` · ${h.capacity}` : ""}</button>)}</div>
                {(() => { const h = dVenue.halls![hallIdx]; return h?.capacity && v.guests && v.guests > h.capacity ? <p className="m4-warn-t">Мало мест: {h.capacity} &lt; {v.guests} гостей</p> : null; })()}</div> : <p className="m4-fine">Залы площадка уточнит в ответе на запрос</p>)}
              <p className="m4-fine">Выбор — ещё не бронь. Цену и доступность подтвердит сервер.</p>
              <div className="m4-detail-act">
                <button type="button" className="m4-btn" onClick={() => void chooseDetail()}>
                  {dVenue ? (dVenue.halls?.[hallIdx] ? `Выбрать зал «${dVenue.halls[hallIdx].name}»` : "Выбрать площадку")
                    : v.artists.includes(dTalent!.id) ? "Убрать из состава" : v.artists.length && !v.artistsDeferred ? (v.artists.length >= 3 ? "Состав полный · 3 из 3" : `Добавить в состав · ${v.artists.length + 1} из 3`) : "Выбрать артиста"}
                </button>
                <a className="m4-link" href={dTalent ? `/artists/${dTalent.id}` : `/venues/${dVenue!.id}`}>Страница {dTalent ? "артиста" : "площадки"}</a>
                <button type="button" className="m4-link" onClick={closeDetail}>← к карусели</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={finRef} className="m4-fin" aria-hidden={fin === "none"}>
        <div ref={finMuted} className="m4-fin-img is-muted" style={{ backgroundImage: `url("${FINALE_IMAGE}")` }} />
        <div ref={finVivid} className="m4-fin-img" style={{ backgroundImage: `url("${FINALE_IMAGE}")` }} />
        <div ref={finGlow} className="m4-fin-glow" />
      </div>
      {(fin === "title" || fin === "buttons") && (
        <div className="m4-fin-text">
          <span className="m4-fin-k">{coreTitle}{v.dateISO ? ` · ${new Date(`${v.dateISO}T12:00:00Z`).getUTCDate()} ${MONTHS[new Date(`${v.dateISO}T12:00:00Z`).getUTCMonth()]}` : ""}</span>
          <h1>{p.submitted?.reused ? "Заявка уже отправлена" : "Заявка отправлена"}</h1>
          <i className="m4-fin-rule" />
          <p>{summary ? `${summary} · ` : ""}исполнители ответят в событии, цена и даты — от сервера</p>
          {fin === "buttons" && <div className="m4-fin-act"><button type="button" className="m4-fin-go" onClick={p.onGoEvent}>Перейти в событие →</button><button type="button" className="m4-fin-home" onClick={p.onGoHome}>На главную</button></div>}
        </div>
      )}
      <div className="m4-sr" aria-live="polite">{say}</div>
    </div>
  );
}

/* party behind frosted glass: silhouettes and clinking glasses (decorative, aria-hidden) */
function Backdrop() {
  const people = useMemo(() => {
    let s = 21; const r = () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
    const rows = [{ base: 70, h: 26, n: 9, op: 0.55 }, { base: 86, h: 38, n: 7, op: 0.72 }, { base: 106, h: 60, n: 4, op: 0.85 }];
    return rows.flatMap((R, ri) => Array.from({ length: R.n }, (_, i) => ({ k: `${ri}-${i}`, x: ((i + 0.3 + r() * 0.5) / R.n) * 100, base: R.base, h: R.h * (0.85 + r() * 0.3), op: R.op, up: r() < 0.35, walk: r() < 0.45, dur: 0.45 + r() * 0.3, wdur: 22 + r() * 18, dist: (r() < 0.5 ? -1 : 1) * (18 + r() * 22), delay: -r() * 10 })));
  }, []);
  const glasses = [[22, 40, 1, 0], [74, 30, 0.85, 1.7], [56, 82, 1.2, 3.1], [86, 70, 0.8, 0.9]];
  return (
    <div className="m4-bg" aria-hidden>
      <div className="m4-party">
        {[0, 1, 2, 3, 4, 5].map((i) => <span key={i} className="m4-light" style={{ "--i": i } as CSSProperties} />)}
        {people.map((q) => (
          <span key={q.k} className={`m4-person${q.walk ? " is-walk" : ""}`} style={{ left: `${q.x}%`, top: `${q.base}%`, height: `${q.h}%`, opacity: q.op, "--dur": `${q.dur}s`, "--wdur": `${q.wdur}s`, "--dist": `${q.dist}vw`, "--delay": `${q.delay}s` } as CSSProperties}>
            <span className={`m4-body${q.up ? " is-up" : ""}`} />
          </span>
        ))}
      </div>
      <div className="m4-toasts">
        {glasses.map(([x, y, s, d], i) => (
          <span key={i} className="m4-pair" style={{ left: `${x}%`, top: `${y}%`, "--s": s, "--d": `${-d}s` } as CSSProperties}>
            <span className="m4-flute is-a" /><span className="m4-flute is-b" /><span className="m4-spark" />
          </span>
        ))}
      </div>
      <div className="m4-glass" />
    </div>
  );
}
