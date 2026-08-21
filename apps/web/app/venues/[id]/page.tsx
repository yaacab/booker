"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getActiveOrg, getToken } from "@/lib/api";
import { CHIP } from "@/lib/copy";
import { formatWhen, money } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { SlotList } from "@/components/SlotList";

type Venue = {
  id: string;
  name: string;
  city: string;
  capacity: number;
  verified: boolean;
  facts: { note: string };
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: { id: string; hall: string; starts_at: string; ends_at?: string; status: string }[];
  halls?: { id?: string; name?: string; capacity?: number }[];
};

type EventOption = { id: string; title: string; event_date: string; city?: string };
type Requirement = { id?: string; category_code: string };

export default function VenuePage({ params }: { params: Promise<{ id: string }> }) {
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

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setDay(q.get("date"));
    const fromEvent = q.get("event");
    if (fromEvent) setEventId(fromEvent);
    setAuthed(Boolean(getToken()));
    void params.then((p) => {
      setVenueId(p.id);
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/venues/${p.id}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Не найдена"))))
        .then(setData)
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
    if (data?.name) document.title = `${data.name} · Букер`;
  }, [data]);

  async function sendToEvent() {
    const id = venueId || data?.id;
    if (!getToken()) {
      router.push(loginHref(id ? `/venues/${id}` : "/search"));
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
      <main>
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

  return (
    <main>
      <p className="kicker">Профиль площадки</p>
      <h1>{data.name}</h1>
      <p>
        {data.city} · до {data.capacity} гостей{" "}
        {data.verified ? <span className="chip ok">{CHIP.verified}</span> : <span className="chip wait">{CHIP.pending}</span>}
      </p>
      <p>{data.facts.note}</p>
      {data.halls?.length ? (
        <>
          <h2>Залы</h2>
          <ul>
            {data.halls.map((hall, i) => (
              <li key={hall.id || hall.name || i}>
                {hall.name}
                {hall.capacity != null ? ` · до ${hall.capacity} гостей` : ""}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <h2>Тарифы</h2>
      <ul>
        {data.tariffs.map((t) => (
          <li key={t.id}>
            {t.title}: {money(t.honorarium_rub)}
          </li>
        ))}
      </ul>
      <h2>Календарь</h2>
      <SlotList slots={data.slots} highlightDay={day} />
      {authed && events.length > 0 ? (
        <label style={{ display: "block", marginTop: 16 }}>
          Событие
          <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
            <option value="">Выберите событие</option>
            {events.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
                {item.event_date ? ` · ${formatWhen(item.event_date)}` : ""}
                {item.city ? ` · ${item.city}` : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {formError ? <p style={{ color: "var(--danger)" }}>{formError}</p> : null}
      <p className="artist-desk-cta" style={{ marginTop: 16 }}>
        {canSend ? (
          <button type="button" onClick={() => void sendToEvent()} disabled={busy}>
            {sendLabel}
          </button>
        ) : (
          <Link className="btn" href={newEventHref}>
            Создать заявку с этой площадкой
          </Link>
        )}
        {canSend ? (
          <>
            {" "}
            <Link className="btn secondary" href={newEventHref}>
              Или создать новое событие
            </Link>
          </>
        ) : null}
      </p>
      <div className="sticky-cta">
        {canSend ? (
          <button type="button" onClick={() => void sendToEvent()} disabled={busy}>
            {sendLabel}
          </button>
        ) : (
          <Link className="btn" href={newEventHref}>
            Создать заявку с этой площадкой
          </Link>
        )}
      </div>
    </main>
  );
}
