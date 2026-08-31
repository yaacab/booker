"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, getActiveOrg, getToken, isWriteRole, setActiveOrg, setToken } from "@/lib/api";
import { CATEGORY, KIND_LABEL, categoryLabel } from "@/lib/copy";
import { formatWhen, money } from "@/lib/format";
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
type ServiceItem = {
  id: string;
  title: string;
  category_code: string;
  description: string;
  honorarium_rub: number | null;
};

const SERVICE_CATEGORIES = Object.keys(CATEGORY);

export default function CabinetPage() {
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [events, setEvents] = useState<EventItem[]>([]);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [bookings, setBookings] = useState<BookingItem[]>([]);
  const [kind, setKind] = useState<string>("");
  const [role, setRole] = useState<string>("");
  const [orgName, setOrgName] = useState("");
  const [ready, setReady] = useState(false);
  const [offerBusy, setOfferBusy] = useState<string | null>(null);
  const [orgId, setOrgId] = useState("");
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [serviceTitle, setServiceTitle] = useState("");
  const [serviceCategory, setServiceCategory] = useState("dj");
  const [serviceDescription, setServiceDescription] = useState("");
  const [serviceHonorarium, setServiceHonorarium] = useState("");
  const [serviceBusy, setServiceBusy] = useState(false);
  const [serviceError, setServiceError] = useState("");
  const [completeness, setCompleteness] = useState<{
    score: number;
    items: { id: string; label: string; done: boolean }[];
    applicable?: boolean;
  } | null>(null);

  async function load() {
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    try {
      const me = await api<{
        email: string;
        is_platform_admin?: boolean;
        organizations?: { id: string; name: string; kind: string; role?: string }[];
        active_organization_id?: string;
      }>("/me");
      setEmail(me.email);
      if (me.is_platform_admin) localStorage.setItem("booker.admin", "1");
      const activeOrgId = getActiveOrg() || me.active_organization_id || me.organizations?.[0]?.id;
      const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
      if (org) {
        setActiveOrg(org.id);
        setOrgId(org.id);
        setKind(org.kind);
        setRole(org.role || "");
        setOrgName(org.name);
      }
      const q = org ? `?organization_id=${encodeURIComponent(org.id)}` : "";
      const loads: Promise<unknown>[] = [
        api<{ items: EventItem[] }>("/events" + q),
        api<{ items: RequestItem[] }>("/requests" + q),
        api<{ items: BookingItem[] }>("/bookings" + q),
      ];
      if (org && (org.kind === "artist" || org.kind === "venue")) {
        loads.push(
          api<{ items: ServiceItem[] }>(`/services?organization_id=${encodeURIComponent(org.id)}`).then((res) => {
            setServices(res.items);
          }),
          api<{ score: number; items: { id: string; label: string; done: boolean }[]; applicable?: boolean }>(
            `/organizations/${encodeURIComponent(org.id)}/supply-completeness`,
          ).then((res) => setCompleteness(res)),
        );
      } else {
        setServices([]);
        setCompleteness(null);
      }
      const [ev, rq, bk] = (await Promise.all(loads.slice(0, 3))) as [
        { items: EventItem[] },
        { items: RequestItem[] },
        { items: BookingItem[] },
      ];
      await Promise.all(loads.slice(3));
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

  async function createService(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!orgId || !isWriteRole(role)) return;
    const title = serviceTitle.trim();
    if (!title) {
      setServiceError("Укажите название");
      return;
    }
    setServiceBusy(true);
    setServiceError("");
    try {
      const body: Record<string, unknown> = {
        organization_id: orgId,
        category_code: serviceCategory,
        title,
        description: serviceDescription.trim(),
      };
      const honorarium = serviceHonorarium.trim();
      if (honorarium) body.honorarium_rub = Number(honorarium);
      const created = await api<ServiceItem>("/services", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setServices((prev) => [...prev, created]);
      setServiceTitle("");
      setServiceDescription("");
      setServiceHonorarium("");
    } catch (err) {
      setServiceError(err instanceof Error ? err.message : "Не удалось создать услугу");
    } finally {
      setServiceBusy(false);
    }
  }

  const showServices = kind === "artist" || kind === "venue";
  const canManageServices = showServices && isWriteRole(role);
  const empty = ready && !error && events.length === 0 && requests.length === 0 && bookings.length === 0;

  function chipCls(status: string): string {
    if (status === "Confirmed" || status === "Completed") return "ok";
    if (status === "Dispute" || status === "Cancelled") return "bad";
    if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
    return "live";
  }

  return (
    <main>
      <p className="kicker">Рабочее пространство · {KIND_LABEL[kind] || "Букер"}</p>
      <h1>{kind === "artist" || kind === "venue" ? "Входящие и сделки" : "Мои события"}</h1>
      {email ? <p className="timeline">{email}{orgName ? ` · ${orgName}` : ""}</p> : null}
      {!ready ? <div className="skeleton" /> : null}
      {error ? (
        <p>
          {error}. <Link href={loginHref("/cabinet")}>Войти</Link>
        </p>
      ) : null}
      {empty ? (
        <article className="card empty">
          <h2>{kind === "artist" || kind === "venue" ? "Пока нет входящих заявок" : "У вас пока нет заявок"}</h2>
          <p>
            {kind === "artist" || kind === "venue"
              ? "Когда заказчик отправит запрос на ваш слот, он появится здесь."
              : "Создайте первую заявку или найдите свободный слот в каталоге. Черновик можно заполнить за несколько минут."}
          </p>
          <p className="timeline">Условия и итоговая сумма появятся в Deal Room после серверного предложения.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {kind === "customer" || !kind ? (
              <Link className="btn" href="/events/new">
                Создать заявку
              </Link>
            ) : null}
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </p>
        </article>
      ) : null}
      {events.length > 0 && kind !== "artist" && kind !== "venue" ? (
        <>
          <h2>События</h2>
          <div className="grid">
            {events.map((e) => (
              <Link className="card" key={e.id} href={`/events/${e.id}`}>
                <strong>{e.title}</strong>
                <div>
                  <span className={`chip ${chipCls(e.status)}`}>{STATUS_LABEL[e.status] || e.status}</span>
                </div>
                <span className="mono">
                  {formatWhen(e.event_date)}
                  {e.city ? ` · ${e.city}` : ""}
                </span>
              </Link>
            ))}
          </div>
        </>
      ) : null}
      {requests.length > 0 && kind !== "customer" ? (
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
                    Открыть Deal Room
                  </Link>
                ) : role === "viewer" ? (
                  <p className="timeline">Только просмотр: оффер отправляет менеджер</p>
                ) : (
                  <button type="button" disabled={offerBusy === r.id} onClick={() => void sendOffer(r)}>
                    {offerBusy === r.id ? "Отправляем…" : "Отправить предложение"}
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
      {showServices ? (
        <>
          {completeness?.applicable ? (
            <article className="card tint">
              <strong>Полнота профиля — {completeness.score}%</strong>
              <ul className="timeline">
                {completeness.items.map((item) => (
                  <li key={item.id}>
                    {item.done ? "✓" : "○"} {item.label}
                  </li>
                ))}
              </ul>
            </article>
          ) : null}
          <h2>Услуги</h2>
          {services.length > 0 ? (
            <ul>
              {services.map((s) => (
                <li key={s.id}>
                  <strong>{s.title}</strong> · {categoryLabel(s.category_code)}
                  {s.honorarium_rub != null ? ` · ${money(s.honorarium_rub)}` : ""}
                  {s.description ? <span className="timeline"> — {s.description}</span> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="timeline">Пока нет услуг в каталоге организации.</p>
          )}
          {canManageServices ? (
            <form className="card" style={{ display: "grid", gap: 12, maxWidth: 420, marginTop: 12 }} onSubmit={createService}>
              <label>
                Название
                <input value={serviceTitle} onChange={(e) => setServiceTitle(e.target.value)} required />
              </label>
              <label>
                Категория
                <select value={serviceCategory} onChange={(e) => setServiceCategory(e.target.value)}>
                  {SERVICE_CATEGORIES.map((code) => (
                    <option key={code} value={code}>
                      {CATEGORY[code]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Описание
                <textarea value={serviceDescription} onChange={(e) => setServiceDescription(e.target.value)} rows={3} />
              </label>
              <label>
                Гонорар, ₽ <span className="timeline">(необязательно)</span>
                <input
                  type="number"
                  min={0}
                  value={serviceHonorarium}
                  onChange={(e) => setServiceHonorarium(e.target.value)}
                />
              </label>
              {serviceError ? <p style={{ color: "var(--danger)" }}>{serviceError}</p> : null}
              <button type="submit" disabled={serviceBusy}>
                {serviceBusy ? "Сохраняем…" : "Добавить услугу"}
              </button>
            </form>
          ) : showServices ? (
            <p className="timeline">Только просмотр: услуги добавляет менеджер.</p>
          ) : null}
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
