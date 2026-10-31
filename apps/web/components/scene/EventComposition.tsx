"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiBase } from "@/lib/api";
import { loadStoredDraft } from "@/components/event-studio/adapter";
import { ProfileMedia } from "@/components/ProfileMedia";
import { formatDay } from "@/lib/format";
import { EASE, MOTION, playArrival, prefersReducedMotion, takeHandoff } from "@/lib/motion";

type Piece = { id: string; name: string; media?: string | null; sub?: string } | null;
type Load = "idle" | "loading" | "ok" | "error";

async function getJson(path: string) {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

/** Visual shell over the existing assembly draft (talentIds / venueId / date).
 *  Reads the same storage the current constructor writes; never books anything. */
export function EventComposition({ date }: { date?: string }) {
  const [artist, setArtist] = useState<Piece>(null);
  const [venue, setVenue] = useState<Piece>(null);
  const [state, setState] = useState<Record<"artist" | "venue", Load>>({ artist: "idle", venue: "idle" });
  const [draftDate, setDraftDate] = useState("");

  useEffect(() => {
    const d = loadStoredDraft()?.draft;
    setDraftDate(d?.date || "");
    const artistId = d?.talentIds?.[d.talentIds.length - 1];
    if (artistId) {
      setState((s) => ({ ...s, artist: "loading" }));
      getJson(`/artists/${artistId}`).then((a) => {
        setArtist({ id: artistId, name: a.presentation?.name || a.name || "Артист", media: a.presentation?.cover_url || a.media_url, sub: a.presentation?.format || "" });
        setState((s) => ({ ...s, artist: "ok" }));
      }).catch(() => setState((s) => ({ ...s, artist: "error" })));
    }
    if (d?.venueId) {
      setState((s) => ({ ...s, venue: "loading" }));
      getJson(`/venues/${d.venueId}`).then((v) => {
        setVenue({ id: d.venueId!, name: v.name || "Площадка", media: v.photos?.[0]?.url || v.media_url, sub: v.capacity ? `до ${v.capacity} гостей` : "" });
        setState((s) => ({ ...s, venue: "ok" }));
      }).catch(() => setState((s) => ({ ...s, venue: "error" })));
    }
  }, []);

  const day = date || draftDate;
  const filled = [artist, venue, day].filter(Boolean).length;
  return (
    <section className="bk-compose" aria-labelledby="bk-compose-title">
      <div className="bk-compose-head">
        <p className="bk-compose-kicker">Ваше событие обретает форму</p>
        <h2 id="bk-compose-title">Композиция события</h2>
        <p className="bk-compose-count" role="status">{filled} из 3 частей · это сборка, не бронь</p>
      </div>
      <div className="bk-compose-stage">
        <div className="bk-compose-table">
          <Slot kind="artist" label="Артист" piece={artist} load={state.artist} href="/search?kind=artist" />
          <Slot kind="venue" label="Площадка" piece={venue} load={state.venue} href="/search?kind=venue" />
          <DateSlot day={day} />
        </div>
      </div>
    </section>
  );
}

function Slot({ kind, label, piece, load, href }: { kind: string; label: string; piece: Piece; load: Load; href: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !piece) return;
    const h = takeHandoff("assembly", (d) => d.id === piece.id);
    if (h) playArrival(el, h.rect, MOTION.related, { depth: true });
    else drop(el);
  }, [piece]);
  if (!piece) {
    return (
      <div className={`bk-slot bk-slot--${kind} is-empty`}>
        <span className="bk-slot-label">{label}</span>
        {load === "loading" ? <span className="bk-slot-skeleton" aria-label="Загружаем" /> :
          load === "error" ? <span className="bk-slot-hint" role="alert">Не удалось загрузить. Выбор сохранён.</span> :
            <a className="bk-slot-hint" href={href}>Выбрать в каталоге →</a>}
      </div>
    );
  }
  return (
    <div ref={ref} className={`bk-slot bk-slot--${kind} is-filled`}>
      <div className="bk-slot-photo"><ProfileMedia src={piece.media} name={piece.name} compact /></div>
      <div className="bk-slot-body"><span className="bk-slot-label">{label}</span><strong>{piece.name}</strong>{piece.sub ? <small>{piece.sub}</small> : null}<a href={href}>Изменить</a></div>
    </div>
  );
}

function DateSlot({ day }: { day: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !day) return;
    if (first.current) { first.current = false; drop(el); return; }
    if (typeof el.animate !== "function") return;
    if (prefersReducedMotion()) { el.animate([{ opacity: 0.4 }, { opacity: 1 }], { duration: MOTION.reduced }); return; }
    /* a calendar leaf turns over onto the new day */
    el.animate([
      { transform: "perspective(900px) rotateX(-92deg)", transformOrigin: "50% 0", opacity: 0.3 },
      { transform: "perspective(900px) rotateX(8deg)", transformOrigin: "50% 0", offset: 0.7 },
      { transform: "perspective(900px) rotateX(0deg)", transformOrigin: "50% 0", opacity: 1 },
    ], { duration: 520, easing: EASE.settle });
  }, [day]);
  if (!day) return <div className="bk-slot bk-slot--date is-empty"><span className="bk-slot-label">Дата</span><span className="bk-slot-hint">Выберите дату ниже</span></div>;
  const d = new Date(`${day}T12:00:00+03:00`);
  return (
    <div ref={ref} className="bk-slot bk-slot--date is-filled">
      <div className="bk-date-leaf" aria-hidden="true"><span>{d.toLocaleDateString("ru-RU", { month: "short", timeZone: "Europe/Moscow" })}</span><b>{d.toLocaleDateString("ru-RU", { day: "numeric", timeZone: "Europe/Moscow" })}</b></div>
      <div className="bk-slot-body"><span className="bk-slot-label">Дата</span><strong>{formatDay(`${day}T12:00:00+03:00`)}</strong><small>Доступность уточнят участники</small></div>
    </div>
  );
}

function drop(el: HTMLElement) {
  if (typeof el.animate !== "function") return;
  if (prefersReducedMotion()) { el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: MOTION.reduced }); return; }
  el.animate([
    { transform: "perspective(1200px) translateZ(70px) translateY(-18px) rotateX(-14deg)", opacity: 0, boxShadow: "0 40px 60px -30px #3a281400" },
    { transform: "perspective(1200px) translateZ(0) translateY(0) rotateX(0)", opacity: 1, boxShadow: "6px 14px 30px -18px #3a281459" },
  ], { duration: 520, easing: EASE.settle });
}
