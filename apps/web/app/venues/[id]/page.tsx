"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getActiveOrg, getToken, isWriteRole } from "@/lib/api";
import { CHIP } from "@/lib/copy";
import { formatWhen, guestsLabel, money } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { SlotList } from "@/components/SlotList";

type Venue = {
  id: string;
  organization_id?: string;
  name: string;
  city: string;
  capacity: number;
  verified: boolean;
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
  const [canManageHalls, setCanManageHalls] = useState(false);
  const [hallName, setHallName] = useState("");
  const [hallCapacity, setHallCapacity] = useState("");
  const [hallBusy, setHallBusy] = useState(false);
  const [hallError, setHallError] = useState("");
  const [halls, setHalls] = useState<HallItem[]>([]);

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
  const synthetic = data.availability_mode === "synthetic";

  return (
    <main>
      <p className="kicker">Профиль площадки</p>
      <h1>{data.name}</h1>
      <p>
        {data.city} · до {guestsLabel(data.capacity)}{" "}
        {synthetic ? (
          <span className="chip wait">{CHIP.syntheticCalendar}</span>
        ) : data.verified ? (
          <span className="chip ok">{CHIP.verified}</span>
        ) : (
          <span className="chip wait">{CHIP.pending}</span>
        )}
      </p>
      {data.address ? (
        <p className="timeline">
          {data.address}
          {data.metro ? ` · м. ${data.metro}` : ""}
          {data.district ? ` · ${data.district}` : ""}
        </p>
      ) : null}
      {data.description ? <p>{data.description}</p> : null}
      {synthetic ? (
        <article className="card tint" role="note">
          <strong>Календарь ориентировочный</strong>
          <p>
            Слоты на 30 дней созданы автоматически для отображения в каталоге. Доступность не подтверждена владельцем
            площадки — перед сделкой оператор уточнит даты.
          </p>
          {data.source_url ? (
            <p className="timeline">
              Источник:{" "}
              <a href={data.source_url} target="_blank" rel="noreferrer noopener">
                {data.source_attribution || "открытые данные"}
              </a>
            </p>
          ) : null}
        </article>
      ) : (
        <p>{data.facts.note}</p>
      )}
      {halls.length ? (
        <>
          <h2>Залы</h2>
          <ul>
            {halls.map((hall, i) => (
              <li key={hall.id || hall.name || i}>
                {hall.name}
                {hall.capacity != null ? ` · до ${hall.capacity} гостей` : ""}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {canManageHalls ? (
        <form className="card" style={{ display: "grid", gap: 12, maxWidth: 420, marginTop: 12 }} onSubmit={createHall}>
          <h2>Добавить зал</h2>
          <label>
            Название
            <input value={hallName} onChange={(e) => setHallName(e.target.value)} required />
          </label>
          <label>
            Вместимость
            <input
              type="number"
              min={1}
              value={hallCapacity}
              onChange={(e) => setHallCapacity(e.target.value)}
              required
            />
          </label>
          {hallError ? <p style={{ color: "var(--danger)" }}>{hallError}</p> : null}
          <button type="submit" disabled={hallBusy}>
            {hallBusy ? "Сохраняем…" : "Создать зал"}
          </button>
        </form>
      ) : null}
      <h2>Тарифы</h2>
      {data.tariffs.length ? (
        <ul>
          {data.tariffs.map((t) => (
            <li key={t.id}>
              {t.title}: {money(t.honorarium_rub)}
              {synthetic ? " · ориентир" : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="timeline">Цена по запросу — итог только в OfferVersion на сервере.</p>
      )}
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
