"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { CATEGORY, KIND_LABEL, categoryLabel } from "@/lib/copy";
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

type DraftItem = {
  id?: string;
  category_code: string;
  qty: number;
  role_label: string;
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
  organization_id?: string;
  requirements?: Requirement[];
  requests?: EventRequest[];
};

const WRITE_ROLES = new Set(["owner", "admin", "manager"]);
const CATEGORY_CODES = Object.keys(CATEGORY);

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

function isClosedRequest(item: EventRequest): boolean {
  return Boolean(item.booking_id) || item.status === "Confirmed";
}

function fillRate(requirements: Requirement[], requests: EventRequest[]): { closed: number; total: number } {
  let total = 0;
  let closed = 0;
  for (const req of requirements) {
    const need = qtyOf(req.qty);
    total += need;
    const filled = requestsForRole(requests, req.id).filter(isClosedRequest).length;
    closed += Math.min(need, filled);
  }
  return { closed, total };
}

function unmatchedRequests(requests: EventRequest[], requirements: Requirement[]): EventRequest[] {
  const ids = new Set(requirements.map((r) => r.id).filter((id): id is string => Boolean(id)));
  return requests.filter((item) => !item.requirement_id || !ids.has(item.requirement_id));
}

function qtyOf(n: number | undefined): number {
  if (!Number.isFinite(n) || !n || n < 1) return 1;
  return Math.min(20, Math.floor(n));
}

function toDraft(items: Requirement[]): DraftItem[] {
  return items.map((item) => ({
    id: item.id,
    category_code: item.category_code,
    qty: qtyOf(item.qty),
    role_label: item.role_label || "",
  }));
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
      {!item.booking_id && item.status !== "Confirmed" ? (
        <span className="timeline"> — сделка ещё не закрыта</span>
      ) : null}
    </p>
  );
}

export default function EventPage() {
  const params = useParams<{ id: string }>();
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [draft, setDraft] = useState<DraftItem[]>([]);
  const [editError, setEditError] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadEvent(id: string) {
    const [data, me] = await Promise.all([
      api<EventDetail>(`/events/${id}`),
      api<{ organizations?: { id: string; role?: string }[] }>("/me"),
    ]);
    setEvent(data);
    setDraft(toDraft(data.requirements ?? []));
    const org = me.organizations?.find((o) => o.id === data.organization_id);
    setCanWrite(WRITE_ROLES.has(org?.role || ""));
    setError("");
  }

  useEffect(() => {
    const id = params.id;
    if (!id) return;
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    loadEvent(id)
      .catch((err: unknown) => {
        setEvent(null);
        setError(err instanceof Error ? err.message : "Событие недоступно");
      })
      .finally(() => setReady(true));
  }, [params.id]);

  useEffect(() => {
    if (event?.title) document.title = `${event.title} · Букер`;
  }, [event?.title]);

  async function saveRequirements() {
    if (!event) return;
    setSaving(true);
    setEditError("");
    try {
      const items = draft
        .filter((item) => item.category_code)
        .map((item) => ({
          ...(item.id ? { id: item.id } : {}),
          category_code: item.category_code,
          qty: qtyOf(item.qty),
          ...(item.role_label.trim() ? { role_label: item.role_label.trim() } : {}),
        }));
      const res = await api<{ requirements: Requirement[] }>(`/events/${event.id}/requirements`, {
        method: "PUT",
        body: JSON.stringify({ items }),
      });
      setEvent((prev) => (prev ? { ...prev, requirements: res.requirements } : prev));
      setDraft(toDraft(res.requirements));
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  function addRow() {
    const code = CATEGORY_CODES.find((c) => !draft.some((d) => d.category_code === c)) || CATEGORY_CODES[0];
    setDraft((rows) => [...rows, { category_code: code, qty: 1, role_label: "" }]);
  }

  function updateRow(index: number, patch: Partial<DraftItem>) {
    setDraft((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function removeRow(index: number) {
    setDraft((rows) => rows.filter((_, i) => i !== index));
  }

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
  const { closed: filledPositions, total: totalPositions } = fillRate(requirements, requests);
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
      {totalPositions > 0 ? (
        <article className="card tint reveal">
          <strong>Закрытие состава</strong>
          <p className="timeline">
            {filledPositions} из {totalPositions} позиций закрыто
            {filledPositions < totalPositions
              ? " — остальные ждут подтверждённую сделку или Deal Room"
              : " — все роли в составе закрыты"}
          </p>
        </article>
      ) : null}
      <p className="timeline">Каждая позиция — своя сделка.</p>
      <h2>Роли</h2>
      {canWrite ? (
        <article className="card">
          <p className="timeline">Редактирование состава. Цена на этом экране не считается.</p>
          {draft.length === 0 ? <p className="timeline">Пока нет позиций — добавьте роль.</p> : null}
          {draft.map((row, index) => (
            <p key={row.id || `draft-${index}`}>
              <label>
                Категория{" "}
                <select
                  value={row.category_code}
                  onChange={(e) => updateRow(index, { category_code: e.target.value })}
                >
                  {CATEGORY_CODES.map((code) => (
                    <option key={code} value={code}>
                      {categoryLabel(code)}
                    </option>
                  ))}
                </select>
              </label>{" "}
              <label>
                Кол-во{" "}
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={row.qty}
                  onChange={(e) => updateRow(index, { qty: qtyOf(Number(e.target.value)) })}
                />
              </label>{" "}
              <label>
                Подпись{" "}
                <input
                  type="text"
                  placeholder="необязательно"
                  value={row.role_label}
                  onChange={(e) => updateRow(index, { role_label: e.target.value })}
                />
              </label>{" "}
              <button type="button" className="secondary" onClick={() => removeRow(index)}>
                Убрать
              </button>
            </p>
          ))}
          <p>
            <button type="button" className="secondary" onClick={addRow}>
              Добавить роль
            </button>{" "}
            <button type="button" disabled={saving} onClick={() => void saveRequirements()}>
              {saving ? "Сохраняем…" : "Сохранить состав"}
            </button>
          </p>
          {editError ? (
            <p className="timeline" role="alert">
              {editError}
            </p>
          ) : null}
        </article>
      ) : null}
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
          <h2>Заявки без роли в составе</h2>
          <article className="card tint">
            <p className="timeline">
              {looseRequests.length} заявок не привязаны к позициям состава — их не видно в карточках ролей выше.
              Привяжите через каталог («Найти на эту дату» у нужной роли) или закройте лишние в Deal Room.
            </p>
            <div className="grid">
              {looseRequests.map((item) => (
                <article className="card" key={item.id}>
                  <strong>{KIND_LABEL[item.resource_type || ""] || item.resource_type || "Заявка"}</strong>
                  <p className="timeline mono">id {item.id.slice(0, 8)}…</p>
                  <RequestDeal item={item} />
                </article>
              ))}
            </div>
          </article>
        </>
      ) : null}
      <p>
        <Link href="/cabinet">Кабинет</Link>
      </p>
    </main>
  );
}
