"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { CHIP, categoryLabel } from "@/lib/copy";
import { formatWhen, money, moscowDate } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { PromoAttributionBeacon } from "@/components/promo/PromoAttributionBeacon";
import { SlotList } from "@/components/SlotList";
import { ProfileMedia } from "@/components/ProfileMedia";

type Slot = { id: string; starts_at: string; ends_at: string; status: string };
type Artist = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified?: boolean;
  media_url?: string | null;
  rider?: Record<string, string>;
  facts: { note: string; deals?: number; response?: string };
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: Slot[];
};
type EventItem = { id: string; title: string; status: string; event_date: string; city?: string };
type Requirement = {
  id?: string;
  category_code: string;
  role_label?: string;
  qty?: number;
  notes?: string;
};
type QuickRequestResult = { event_id?: string; request_id?: string; status?: string };

const CAT: Record<string, string> = { dj: "DJ-сет", host: "Ведущий", cover: "Кавер" };

function requirementLabel(req: Requirement): string {
  const label = categoryLabel(req.category_code) || req.role_label || req.category_code;
  return req.qty && req.qty > 1 ? `${label} · ${req.qty} чел.` : label;
}

export function ArtistProfileClient() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Artist | null>(null);
  const [error, setError] = useState("");
  const [slotId, setSlotId] = useState("");
  const [busy, setBusy] = useState(false);
  const [wantedDay, setWantedDay] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventId, setEventId] = useState("");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [requirementId, setRequirementId] = useState("");
  const [catalogHref, setCatalogHref] = useState("/search");

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const backQuery = new URLSearchParams(q);
    backQuery.delete("slot");
    setCatalogHref(`/search${backQuery.size ? `?${backQuery.toString()}` : ""}`);
    const wanted = q.get("slot");
    const day = q.get("date");
    const fromEvent = q.get("event");
    const fromReq = q.get("requirement");
    setWantedDay(day);
    if (fromEvent) setEventId(fromEvent);
    if (fromReq) setRequirementId(fromReq);
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/artists/${params.id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Не найден"))))
      .then((json: Artist) => {
        setData(json);
        const day = q.get("date");
        const live = json.slots.filter(
          (s) => !s.ends_at || new Date(s.ends_at).getTime() >= Date.now()
        );
        const fromUrl = live.find((s) => s.id === wanted && s.status === "open");
        const fromDay = day
          ? live.find((s) => s.status === "open" && moscowDate(s.starts_at) === day)
          : undefined;
        const open = fromUrl || fromDay || live.find((s) => s.status === "open");
        if (open) setSlotId(open.id);
      })
      .catch((err: Error) => setError(err.message));
  }, [params.id]);

  useEffect(() => {
    if (!getToken()) {
      setSignedIn(false);
      setEvents([]);
      return;
    }
    setSignedIn(true);
    let cancelled = false;
    api<{ items: EventItem[] }>("/events")
      .then((res) => {
        if (!cancelled) setEvents(res.items || []);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!eventId || !getToken()) {
      setRequirements([]);
      return;
    }
    let cancelled = false;
    api<{ requirements?: Requirement[] }>(`/events/${eventId}`)
      .then((detail) => {
        if (cancelled) return;
        const items = detail.requirements || [];
        setRequirements(items);
        setRequirementId((current) => (current && items.some((r) => r.id === current) ? current : ""));
      })
      .catch(() => {
        if (!cancelled) setRequirements([]);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  useEffect(() => {
    if (data?.name) document.title = `${data.name} · Букер`;
  }, [data]);

  async function request() {
    if (!getToken()) {
      const q = new URLSearchParams(window.location.search);
      if (slotId) q.set("slot", slotId);
      const qs = q.toString();
      router.push(loginHref(`/artists/${params.id}${qs ? `?${qs}` : ""}`));
      return;
    }
    if (!slotId) {
      setError("Нет свободного слота");
      return;
    }
    const body: { artist_id: string; slot_id: string; event_id?: string; requirement_id?: string } = {
      artist_id: params.id,
      slot_id: slotId,
    };
    if (eventId) {
      body.event_id = eventId;
      if (requirementId) body.requirement_id = requirementId;
    }
    try {
      setBusy(true);
      const created = await api<QuickRequestResult>("/quick-request", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const known = eventId || created.event_id;
      router.push(known ? `/events/${encodeURIComponent(known)}` : "/cabinet");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка заявки");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <main className="public-profile-reference">
        <h1>Профиль</h1>
        <p>{error || ""}</p>
        {!error ? (
          <div className="grid">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : null}
      </main>
    );
  }

  const rider = data.rider || {};
  const selectableRequirements = requirements.filter((req): req is Requirement & { id: string } => Boolean(req.id));

  const liveOpenSlots = data.slots.filter((slot) => slot.status === "open" && (!slot.ends_at || new Date(slot.ends_at).getTime() >= Date.now()));
  const selectedSlot = data.slots.find((slot) => slot.id === slotId);

  return (
    <main className="public-profile-reference artist-profile-reference page-enter">
      <Suspense fallback={null}>
        <PromoAttributionBeacon kind="artist" profileId={data.id} />
      </Suspense>
      <Link className="profile-back" href={catalogHref}><span aria-hidden="true">←</span> К поиску артистов</Link>
      <div className="public-profile-layout">
        <aside className="public-profile-rail">
          <ProfileMedia src={data.media_url} name={data.name} />
          <section className="profile-calendar-panel" aria-labelledby="artist-calendar-heading">
            <div className="profile-section-heading"><h2 id="artist-calendar-heading">Ближайшие даты</h2><span>МСК</span></div>
            <SlotList slots={data.slots} value={slotId} onChange={setSlotId} selectable highlightDay={wantedDay} />
            {!liveOpenSlots.length ? <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Нет%20слота">Связаться с оператором</a> : <p className="profile-small-note">Выберите свободное время для заявки.</p>}
          </section>
        </aside>
        <div className="public-profile-content">
          <header className="public-profile-heading">
            <div>
              <p className="profile-eyebrow">{categoryLabel(data.category) || CAT[data.category] || "Артист"}</p>
              <h1>{data.name}{data.verified ? <span className="profile-verified-mark" role="img" aria-label={CHIP.verified} title={CHIP.verified}>✓</span> : null}</h1>
              <p className="profile-location"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></svg>{data.city}</p>
              {!data.verified ? <span className="chip wait">{CHIP.pending}</span> : null}
            </div>
            <div className="public-profile-actions">
              <a className="btn profile-primary-action" href="#profile-booking">Добавить в событие <span aria-hidden="true">→</span></a>
              <div className="profile-secondary-actions"><FavoriteToggle targetType="artist" targetId={data.id} /><Link className="btn secondary" href={`/artists/${data.id}/share`}>Поделиться <span aria-hidden="true">↗</span></Link></div>
            </div>
          </header>

          <dl className="profile-facts-strip">
            <div><dt>Завершённых сделок</dt><dd>{data.facts.deals ?? 0}</dd></div>
            <div><dt>Свободных слотов</dt><dd>{liveOpenSlots.length}</dd></div>
            <div className="profile-fact-response"><dt>Обычно отвечает</dt><dd>{data.facts.response || "Пока нет данных"}</dd></div>
          </dl>

          <section className="public-profile-section">
            <h2>Об артисте</h2>
            <p>{rider.about || data.facts.note}</p>
            <div className="profile-fact-chips"><span>{rider.format || CAT[data.category] || categoryLabel(data.category)}</span>{rider.lineup ? <span>{rider.lineup}</span> : null}</div>
          </section>

          <section className="public-profile-section">
            <div className="profile-section-heading"><h2>Формат и стоимость</h2><span>Предварительные условия</span></div>
            {data.tariffs.length ? <ul className="profile-tariff-list">{data.tariffs.map((tariff) => <li key={tariff.id}><span>{tariff.title}</span><strong>{money(tariff.honorarium_rub)}</strong></li>)}</ul> : <p className="timeline">Стоимость уточняется по запросу.</p>}
            <p className="profile-small-note">Окончательная стоимость и условия — в предложении после заявки.</p>
          </section>

          <section className="public-profile-section profile-rider-section">
            <h2>Технический райдер</h2>
            <div className="profile-rider-card"><svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M8 8v8M12 8v8M16 8v8M6 11h4M10 14h4M14 10h4" /></svg><p>{rider.tech || "Технические требования и состав согласуем после заявки."}</p></div>
          </section>

          <section className="profile-booking-panel" id="profile-booking" aria-labelledby="artist-booking-heading">
            <div className="profile-section-heading"><h2 id="artist-booking-heading">Пригласить на событие</h2><span aria-hidden="true">↗</span></div>
            <p className="profile-booking-date">{selectedSlot ? formatWhen(selectedSlot.starts_at) : "Выберите свободную дату в календаре"}</p>
            {signedIn ? <div className="profile-booking-fields">
              <label>Событие<select value={eventId} onChange={(e) => setEventId(e.target.value)} aria-label="Событие"><option value="">Новая заявка без события</option>{events.map((ev) => <option key={ev.id} value={ev.id}>{ev.title}{ev.event_date ? ` · ${formatWhen(ev.event_date)}` : ""}</option>)}</select></label>
              {eventId ? <label>Роль<select value={requirementId} onChange={(e) => setRequirementId(e.target.value)} aria-label="Роль в событии"><option value="">Без привязки к роли</option>{selectableRequirements.map((req) => <option key={req.id} value={req.id}>{requirementLabel(req)}</option>)}</select></label> : null}
            </div> : null}
            {error ? <p className="profile-error" role="alert">{error}</p> : null}
            <button className="btn profile-primary-action" type="button" onClick={() => void request()} disabled={!slotId || busy}>{busy ? "Отправляем заявку…" : "Запросить предложение"}<span aria-hidden="true">→</span></button>
            <p className="profile-small-note">Отправьте заявку, чтобы согласовать детали и получить предложение.</p>
          </section>
        </div>
      </div>
      <div className="sticky-cta"><button type="button" onClick={() => void request()} disabled={!slotId || busy}>{busy ? "Отправляем заявку…" : "Запросить предложение"}</button></div>
    </main>
  );
}
