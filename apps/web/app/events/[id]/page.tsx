"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { KIND_LABEL, categoryLabel } from "@/lib/copy";
import { formatWhen, moscowDate } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { STATUS_LABEL } from "@/lib/status";

type Requirement = {
  id?: string;
  category_code: string;
  role_label?: string;
  qty?: number;
  notes?: string;
};

type EventRequest = {
  id: string;
  status: string;
  resource_type?: string;
  resource_id?: string;
  requirement_id?: string | null;
  booking_id?: string | null;
};

type EventDetail = {
  id: string;
  title: string;
  status: string;
  city?: string;
  event_date: string;
  guest_count?: number;
  requirements?: Requirement[];
  requests?: EventRequest[];
};

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

function searchHref(date: string, category: string, city?: string, eventId?: string, requirementId?: string): string {
  const q = new URLSearchParams({ date });
  if (category) q.set("category", category);
  if (city) q.set("city", city);
  if (eventId) q.set("event", eventId);
  if (requirementId) q.set("requirement", requirementId);
  return `/search?${q.toString()}`;
}

function requestsForRole(requests: EventRequest[], requirementId?: string): EventRequest[] {
  if (!requirementId) return [];
  return requests.filter((item) => item.requirement_id === requirementId);
}

function unmatchedRequests(requests: EventRequest[], requirements: Requirement[]): EventRequest[] {
  const ids = new Set(requirements.map((r) => r.id).filter((id): id is string => Boolean(id)));
  return requests.filter((item) => !item.requirement_id || !ids.has(item.requirement_id));
}

function RequestDeal({ item }: { item: EventRequest }) {
  return (
    <p className="timeline">
      <span className={`chip ${chipCls(item.status)}`}>{STATUS_LABEL[item.status] || item.status}</span>
      {item.booking_id ? (
        <>
          {" "}
          <Link href={`/deals/${item.booking_id}`}>Открыть Deal Room</Link>
        </>
      ) : null}
    </p>
  );
}

export default function EventPage() {
  const params = useParams<{ id: string }>();
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const id = params.id;
    if (!id) return;
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    api<EventDetail>(`/events/${id}`)
      .then((data) => {
        setEvent(data);
        setError("");
      })
      .catch((err: unknown) => {
        setEvent(null);
        setError(err instanceof Error ? err.message : "Событие недоступно");
      })
      .finally(() => setReady(true));
  }, [params.id]);

  useEffect(() => {
    if (event?.title) document.title = `${event.title} · Букер`;
  }, [event?.title]);

  if (!ready) {
    return (
      <main>
        <p className="kicker">Событие</p>
        <h1>Событие</h1>
        <div className="skeleton" style={{ minHeight: 180 }} />
      </main>
    );
  }

  if (error || !event) {
    return (
      <main>
        <p className="kicker">Событие</p>
        <h1>Событие</h1>
        <p>
          {error || "Событие недоступно"}
          {error === "Нужен вход" || error === "Нужна авторизация" || error === "Сессия недействительна" ? (
            <>
              . <Link href={loginHref(`/events/${params.id}`)}>Войти</Link>
            </>
          ) : null}
        </p>
        <p>
          <Link href="/cabinet">Вернуться в кабинет</Link>
        </p>
      </main>
    );
  }

  const requirements = event.requirements ?? [];
  const requests = event.requests ?? [];
  const looseRequests = unmatchedRequests(requests, requirements);
  const date = moscowDate(event.event_date);

  return (
    <main>
      <p className="kicker">Состав события</p>
      <h1>{event.title}</h1>
      <div>
        <span className={`chip ${chipCls(event.status)}`}>{STATUS_LABEL[event.status] || event.status}</span>
      </div>
      <p className="mono">
        {formatWhen(event.event_date)}
        {event.city ? ` · ${event.city}` : ""}
        {event.guest_count ? ` · ${event.guest_count} гостей` : ""}
      </p>
      <p className="timeline">Каждая позиция — своя сделка.</p>
      <h2>Роли</h2>
      {requirements.length === 0 ? (
        <p className="timeline">Состав пока не указан. Добавьте роли в заявке — цена на этом экране не считается.</p>
      ) : (
        <div className="grid">
          {requirements.map((req, i) => {
            const code = req.category_code;
            const label = categoryLabel(code) || req.role_label || code;
            const roleRequests = requestsForRole(requests, req.id);
            return (
              <article className="card" key={req.id || `${code}-${i}`}>
                <strong>{label}</strong>
                {req.qty && req.qty > 1 ? <p className="timeline">{req.qty} чел.</p> : null}
                {req.notes ? <p className="timeline">{req.notes}</p> : null}
                {roleRequests.map((item) => (
                  <RequestDeal key={item.id} item={item} />
                ))}
                <p>
                  <Link href={searchHref(date, code, event.city, event.id, req.id)}>Найти на эту дату</Link>
                </p>
              </article>
            );
          })}
        </div>
      )}
      {looseRequests.length > 0 ? (
        <>
          <h2>Заявки</h2>
          <div className="grid">
            {looseRequests.map((item) => (
              <article className="card" key={item.id}>
                <strong>{KIND_LABEL[item.resource_type || ""] || item.resource_type || "Заявка"}</strong>
                <RequestDeal item={item} />
              </article>
            ))}
          </div>
        </>
      ) : null}
      <p>
        <Link href="/cabinet">Кабинет</Link>
      </p>
    </main>
  );
}
