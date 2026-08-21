"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import { formatWhen, money, moscowDate } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { STATUS_LABEL } from "@/lib/status";

type EventItem = { id: string; title: string; status: string; event_date: string; city?: string };
type RequestItem = {
  id: string;
  status: string;
  event_title: string;
  offer_id: string | null;
  booking_id: string | null;
  slot_id: string | null;
  honorarium_rub: number;
};
type BookingItem = { id: string; status: string; event_title: string; event_date?: string };

export default function CabinetPage() {
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [events, setEvents] = useState<EventItem[]>([]);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [bookings, setBookings] = useState<BookingItem[]>([]);
  const [ready, setReady] = useState(false);
  const [offerBusy, setOfferBusy] = useState<string | null>(null);

  async function load() {
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    try {
      const me = await api<{ email: string; is_platform_admin?: boolean }>("/me");
      setEmail(me.email);
      if (me.is_platform_admin) localStorage.setItem("booker.admin", "1");
      const [ev, rq, bk] = await Promise.all([
        api<{ items: EventItem[] }>("/events"),
        api<{ items: RequestItem[] }>("/requests"),
        api<{ items: BookingItem[] }>("/bookings"),
      ]);
      setEvents(ev.items);
      setRequests(rq.items);
      setBookings(bk.items);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setReady(true);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function sendOffer(item: RequestItem) {
    if (!item.slot_id) {
      setError("Нет свободного слота для оффера");
      return;
    }
    setOfferBusy(item.id);
    try {
      const res = await api<{ booking_id: string }>("/requests/" + item.id + "/offers", {
        method: "POST",
        body: JSON.stringify({ honorarium_rub: item.honorarium_rub, slot_id: item.slot_id }),
      });
      window.location.href = `/deals/${res.booking_id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось ответить");
    } finally {
      setOfferBusy(null);
    }
  }

  const empty = ready && !error && events.length === 0 && requests.length === 0 && bookings.length === 0;

  function chipCls(status: string): string {
    if (status === "Confirmed" || status === "Completed") return "ok";
    if (status === "Dispute" || status === "Cancelled") return "bad";
    if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
    return "live";
  }

  return (
    <main>
      <p className="kicker">Очередь</p>
      <h1>Что горит</h1>
      {email ? <p className="timeline">{email}</p> : null}
      {!ready ? <div className="skeleton" /> : null}
      {error ? (
        <p>
          {error}. <Link href={loginHref("/cabinet")}>Войти</Link>
        </p>
      ) : null}
      {empty ? (
        <article className="card empty">
          <h2>Пока тихо. Подозрительно.</h2>
          <p>Соберите вечер или найдите дырку в календаре. Пустой кабинет — не дзен, а недоделка.</p>
          <p className="timeline">Первая сделка в контуре — комиссия платформы 0. Гонорар как обычно.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn" href="/events/new">
              Собрать вечер
            </Link>
            <Link className="btn secondary" href="/search">
              Кто ещё не занят
            </Link>
          </p>
        </article>
      ) : null}
      {events.length > 0 ? (
        <>
          <h2>События</h2>
          <div className="grid">
            {events.map((e) => (
              <article className="card" key={e.id}>
                <strong>{e.title}</strong>
                <div>
                  <span className={`chip ${chipCls(e.status)}`}>{STATUS_LABEL[e.status] || e.status}</span>
                </div>
                <div className="mono">
                  {formatWhen(e.event_date)}
                  {e.city ? ` · ${e.city}` : ""}
                </div>
                <p>
                  <Link href={`/search?date=${moscowDate(e.event_date)}${e.city ? `&city=${encodeURIComponent(e.city)}` : ""}`}>
                    Кто ещё не занят на эту дату
                  </Link>
                </p>
              </article>
            ))}
          </div>
        </>
      ) : null}
      {requests.length > 0 ? (
        <>
          <h2>Входящие заявки</h2>
          <div className="grid">
            {requests.map((r) => (
              <article className="card" key={r.id}>
                <strong>{r.event_title}</strong>
                <div>
                  <span className={`chip ${chipCls(r.status)}`}>{STATUS_LABEL[r.status] || r.status}</span>
                </div>
                <p className="timeline">витрина {money(r.honorarium_rub)} — это ещё не счёт</p>
                {r.booking_id ? (
                  <Link className="btn" href={`/deals/${r.booking_id}`}>
                    В гримёрку
                  </Link>
                ) : (
                  <button type="button" disabled={offerBusy === r.id} onClick={() => void sendOffer(r)}>
                    {offerBusy === r.id ? "Считаем…" : "Ответить цифрой"}
                  </button>
                )}
              </article>
            ))}
          </div>
        </>
      ) : null}
      {bookings.length > 0 ? (
        <>
          <h2>Сделки</h2>
          <div className="grid">
            {bookings.map((b) => (
              <Link className="card" key={b.id} href={`/deals/${b.id}`}>
                <strong>{b.event_title}</strong>
                <div>
                  <span className={`chip ${chipCls(b.status)}`}>{STATUS_LABEL[b.status] || b.status}</span>
                </div>
                <span className="mono">{b.event_date ? formatWhen(b.event_date) : `сделка ${b.id.slice(0, 8)}`}</span>
              </Link>
            ))}
          </div>
        </>
      ) : null}
      <p>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setToken(null);
            localStorage.removeItem("booker.admin");
            window.location.href = "/login";
          }}
        >
          Выйти
        </button>
      </p>
    </main>
  );
}
