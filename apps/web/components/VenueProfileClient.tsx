"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getActiveOrg, getToken, isWriteRole } from "@/lib/api";
import { CHIP } from "@/lib/copy";
import { formatWhen, guestsLabel, money } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { PromoAttributionBeacon } from "@/components/promo/PromoAttributionBeacon";
import { SlotList } from "@/components/SlotList";
import { ProfileMedia } from "@/components/ProfileMedia";

type Venue = {
  id: string;
  organization_id?: string;
  name: string;
  city: string;
  capacity: number;
  verified: boolean;
  media_url?: string | null;
  address?: string;
  district?: string;
  metro?: string;
  description?: string;
  source_url?: string;
  source_attribution?: string;
  listing_origin?: string;
  availability_mode?: string;
  facts: { note: string };
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: { id: string; hall: string; starts_at: string; ends_at?: string; status: string }[];
  halls?: { id?: string; name?: string; capacity?: number }[];
};

type HallItem = { id: string; name: string; capacity: number };
type EventOption = { id: string; title: string; event_date: string; city?: string };
type Requirement = { id?: string; category_code: string };

export function VenueProfileClient({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const [venueId, setVenueId] = useState("");
  const [data, setData] = useState<Venue | null>(null);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const [authed, setAuthed] = useState(false);
  const [events, setEvents] = useState<EventOption[]>([]);
  const [eventId, setEventId] = useState("");
  const [requirementId, setRequirementId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [canManageHalls, setCanManageHalls] = useState(false);
  const [hallName, setHallName] = useState("");
  const [hallCapacity, setHallCapacity] = useState("");
  const [hallBusy, setHallBusy] = useState(false);
  const [hallError, setHallError] = useState("");
  const [halls, setHalls] = useState<HallItem[]>([]);
  const [catalogHref, setCatalogHref] = useState("/search?kind=venue");

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const backQuery = new URLSearchParams(q);
    backQuery.delete("slot");
    if (!backQuery.has("kind")) backQuery.set("kind", "venue");
    setCatalogHref(`/search?${backQuery.toString()}`);
    setDay(q.get("date"));
    const fromEvent = q.get("event");
    if (fromEvent) setEventId(fromEvent);
    setAuthed(Boolean(getToken()));
    void params.then((p) => {
      setVenueId(p.id);
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/venues/${p.id}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Не найдена"))))
        .then((venue: Venue) => {
          setData(venue);
          setHalls((venue.halls || []) as HallItem[]);
        })
        .catch((e: Error) => setError(e.message));
    });
  }, [params]);

  useEffect(() => {
    if (!getToken()) return;
    const org = getActiveOrg();
    const q = org ? `?organization_id=${encodeURIComponent(org)}` : "";
    api<{ items: EventOption[] }>("/events" + q)
      .then((res) => {
        setEvents(res.items);
        setEventId((current) => current || (res.items.length === 1 ? res.items[0].id : ""));
      })
      .catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    if (!eventId || !getToken()) {
      setRequirementId(null);
      return;
    }
    let cancelled = false;
    api<{ requirements?: Requirement[] }>(`/events/${eventId}`)
      .then((ev) => {
        if (cancelled) return;
        const venueReq = (ev.requirements || []).find((r) => r.category_code === "venue" && r.id);
        setRequirementId(venueReq?.id || null);
      })
      .catch(() => {
        if (!cancelled) setRequirementId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  useEffect(() => {
    if (!getToken() || !data?.organization_id) {
      setCanManageHalls(false);
      return;
    }
    let cancelled = false;
    api<{ organizations?: { id: string; kind: string; role?: string }[] }>("/me")
      .then((me) => {
        if (cancelled) return;
        const orgId = getActiveOrg() || me.organizations?.[0]?.id;
        const org = me.organizations?.find((o) => o.id === orgId) || me.organizations?.[0];
        setCanManageHalls(
          Boolean(
            org &&
              org.kind === "venue" &&
              org.id === data.organization_id &&
              isWriteRole(org.role),
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setCanManageHalls(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data?.organization_id]);

  useEffect(() => {
    if (data?.name) document.title = `${data.name} · Букер`;
  }, [data]);

  async function createHall(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const id = venueId || data?.id;
    if (!id) return;
    const name = hallName.trim();
    if (!name) {
      setHallError("Укажите название зала");
      return;
    }
    if (!hallCapacity.trim()) {
      setHallError("Укажите вместимость");
      return;
    }
    setHallBusy(true);
    setHallError("");
    try {
      const created = await api<HallItem>(`/venues/${id}/halls`, {
        method: "POST",
        body: JSON.stringify({ name, capacity: Number(hallCapacity) }),
      });
      setHalls((prev) => [...prev, created]);
      setHallName("");
      setHallCapacity("");
    } catch (err) {
      setHallError(err instanceof Error ? err.message : "Не удалось создать зал");
    } finally {
      setHallBusy(false);
    }
  }

  async function sendToEvent() {
    const id = venueId || data?.id;
    if (!getToken()) {
      const q = new URLSearchParams(window.location.search);
      const qs = q.toString();
      router.push(loginHref(id ? `/venues/${id}${qs ? `?${qs}` : ""}` : "/search"));
      return;
    }
    if (!id || !eventId) {
      setFormError("Выберите событие");
      return;
    }
    try {
      setBusy(true);
      setFormError("");
      const body: { resource_type: string; resource_id: string; requirement_id?: string } = {
        resource_type: "venue",
        resource_id: id,
      };
      if (requirementId) body.requirement_id = requirementId;
      await api(`/events/${eventId}/requests`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      router.push(`/events/${eventId}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Ошибка заявки");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <main className="public-profile-reference">
        <h1>Площадка</h1>
        <p>{error || ""}</p>
        {!error ? (
          <div className="grid">
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : null}
      </main>
    );
  }

  const newEventHref = `/events/new?venue=need&roof=${encodeURIComponent(data.name)}`;
  const canSend = authed && Boolean(eventId);
  const sendLabel = busy ? "Отправляем…" : "Отправить в событие";
  const synthetic = data.availability_mode === "synthetic";

  return (
    <main className="public-profile-reference venue-profile-reference page-enter">
      <Suspense fallback={null}>
        <PromoAttributionBeacon kind="venue" profileId={data.id} />
      </Suspense>
      <Link className="profile-back" href={catalogHref}><span aria-hidden="true">←</span> К поиску площадок</Link>
      <div className="public-profile-layout">
        <aside className="public-profile-rail">
          <ProfileMedia src={data.media_url} name={data.name} />
          <section className="profile-calendar-panel" aria-labelledby="venue-calendar-heading">
            <div className="profile-section-heading"><h2 id="venue-calendar-heading">Ближайшие даты</h2><span>МСК</span></div>
            {synthetic ? <p className="profile-calendar-notice">Календарь ориентировочный. Доступность уточнит оператор.</p> : null}
            <SlotList slots={data.slots} highlightDay={day} />
          </section>
        </aside>
        <div className="public-profile-content">
          <header className="public-profile-heading">
            <div>
              <p className="profile-eyebrow">Площадка для событий</p>
              <h1>{data.name}{data.verified ? <span className="profile-verified-mark" role="img" aria-label={CHIP.verified} title={CHIP.verified}>✓</span> : null}</h1>
              <p className="profile-location"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></svg>{data.city}{data.address ? ` · ${data.address}` : ""}</p>
              {data.metro || data.district ? <p className="profile-location-detail">{data.metro ? `м. ${data.metro}` : ""}{data.metro && data.district ? " · " : ""}{data.district}</p> : null}
              {data.listing_origin === "open_data" ? <span className="chip wait">{CHIP.openDataVenue}</span> : synthetic ? <span className="chip wait">{CHIP.syntheticCalendar}</span> : !data.verified ? <span className="chip wait">{CHIP.pending}</span> : null}
            </div>
            <div className="public-profile-actions">
              <a className="btn profile-primary-action" href="#profile-booking">Добавить в событие <span aria-hidden="true">→</span></a>
              <div className="profile-secondary-actions"><FavoriteToggle targetType="venue" targetId={data.id} /><Link className="btn secondary" href={`/venues/${data.id}/share`}>Поделиться <span aria-hidden="true">↗</span></Link></div>
            </div>
          </header>

          <dl className="profile-facts-strip">
            <div><dt>Вместимость</dt><dd>{data.capacity ? `До ${guestsLabel(data.capacity)}` : "Уточняется"}</dd></div>
            <div><dt>Залов в профиле</dt><dd>{halls.length}</dd></div>
            <div className="profile-fact-response"><dt>Профиль</dt><dd>{data.verified ? "Подтверждён" : "Не подтверждён"}</dd></div>
          </dl>

          <section className="public-profile-section">
            <h2>О площадке</h2>
            <p>{data.description || (synthetic ? "Детали площадки и доступные даты можно уточнить через оператора." : data.facts.note)}</p>
            {synthetic ? <div className="profile-calendar-notice" role="note"><strong>Календарь ориентировочный</strong><p>Доступность не подтверждена владельцем площадки. Перед бронированием оператор уточнит даты.</p>{data.source_url ? <p className="profile-source-link">Источник: <a href={data.source_url} target="_blank" rel="noreferrer noopener">{data.source_attribution || "открытые данные"} ↗</a></p> : null}</div> : null}
          </section>

          {halls.length ? <section className="public-profile-section">
            <div className="profile-section-heading"><h2>Залы и вместимость</h2><span>{halls.length} в профиле</span></div>
            <ul className="profile-hall-grid">{halls.map((hall, index) => <li key={hall.id || hall.name || index}><div className="profile-hall-icon" aria-hidden="true"><svg viewBox="0 0 80 72"><path d="M12 61V20h56v41M8 61h64M25 20V11h30v9M31 61V45h18v16" /><rect x="21" y="29" width="9" height="8" rx="1" /><rect x="50" y="29" width="9" height="8" rx="1" /><path d="M36 11V6h8v5" /></svg><span>{String(index + 1).padStart(2, "0")}</span></div><strong>{hall.name || `Зал ${index + 1}`}</strong>{hall.capacity != null ? <span>До {guestsLabel(hall.capacity)}</span> : <span>Вместимость уточняется</span>}</li>)}</ul>
          </section> : null}

          {canManageHalls ? <form className="profile-booking-panel profile-hall-form" onSubmit={createHall}>
            <h2>Добавить зал</h2>
            <div className="profile-booking-fields"><label>Название<input value={hallName} onChange={(e) => setHallName(e.target.value)} required /></label><label>Вместимость<input type="number" min={1} value={hallCapacity} onChange={(e) => setHallCapacity(e.target.value)} required /></label></div>
            {hallError ? <p className="profile-error" role="alert">{hallError}</p> : null}
            <button type="submit" disabled={hallBusy}>{hallBusy ? "Сохраняем…" : "Создать зал"}</button>
          </form> : null}

          <section className="public-profile-section">
            <div className="profile-section-heading"><h2>Стоимость аренды</h2><span>Предварительные условия</span></div>
            {data.tariffs.length ? <ul className="profile-tariff-list">{data.tariffs.map((tariff) => <li key={tariff.id}><span>{tariff.title}</span><strong>{money(tariff.honorarium_rub)}{synthetic ? <small>Ориентир</small> : null}</strong></li>)}</ul> : <p className="timeline">Цена по запросу.</p>}
            <p className="profile-small-note">Окончательная стоимость и условия — в предложении после заявки.</p>
          </section>

          <section className="profile-booking-panel" id="profile-booking" aria-labelledby="venue-booking-heading">
            <div className="profile-section-heading"><h2 id="venue-booking-heading">Ваше событие здесь</h2><span aria-hidden="true">↗</span></div>
            <p>Добавьте площадку в событие, чтобы согласовать дату и условия.</p>
            {authed && events.length > 0 ? <label>Событие<select value={eventId} onChange={(e) => setEventId(e.target.value)}><option value="">Выберите событие</option>{events.map((item) => <option key={item.id} value={item.id}>{item.title}{item.event_date ? ` · ${formatWhen(item.event_date)}` : ""}{item.city ? ` · ${item.city}` : ""}</option>)}</select></label> : null}
            {formError ? <p className="profile-error" role="alert">{formError}</p> : null}
            <div className="profile-booking-actions">{canSend ? <button className="btn profile-primary-action" type="button" onClick={() => void sendToEvent()} disabled={busy}>{sendLabel}<span aria-hidden="true">→</span></button> : <Link className="btn profile-primary-action" href={newEventHref}>Создать заявку с этой площадкой<span aria-hidden="true">→</span></Link>}{canSend ? <Link className="profile-text-link" href={newEventHref}>Или создать новое событие ↗</Link> : null}</div>
          </section>
        </div>
      </div>
      <div className="sticky-cta">{canSend ? <button type="button" onClick={() => void sendToEvent()} disabled={busy}>{sendLabel}</button> : <Link className="btn" href={newEventHref}>Создать заявку с этой площадкой</Link>}</div>
    </main>
  );
}
