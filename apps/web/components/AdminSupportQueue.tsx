"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatSupportDeadline, supportDeadlineLabel, SUPPORT_HOURS_TEXT } from "@/lib/supportSla";
import {
  safeSupportSubject,
  stableSupportKey,
  supportQueueAge,
  supportQueueHeaders,
  supportQueuePath,
  supportTicketPath,
  type StableSupportKey,
  type SupportNote,
  type SupportQueueFilters,
  type SupportTicket,
  type SupportTicketDetail,
} from "@/lib/supportQueue";

type QueueResponse = {
  items: SupportTicket[];
  total?: number;
  open_count?: number;
  overdue_count?: number;
};
type SupportStaff = { id: string; name: string; role: "operator" | "administrator" };

const DEFAULT_FILTERS: SupportQueueFilters = {
  state: "all", overdue: false, priority: "all", category: "all",
  assignedToMe: false, limit: 20, offset: 0,
};
const STATES = ["all", "active", "open", "waiting_for_support", "waiting_for_user", "resolved", "closed"];
const CATEGORIES = ["all", "profile", "brief", "message", "review", "media", "payment", "incident", "technical", "other"];
const GRID_STYLE = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))", gap: "1rem" };

function readableError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) return "Доступ к очереди не подтверждён. Проверьте права и код 2FA.";
    if (error.status === 409) return "Обращение изменилось. Данные обновлены; проверьте их перед повторным действием.";
  }
  return "Не удалось выполнить действие. Проверьте соединение и попробуйте ещё раз.";
}

export default function AdminSupportQueue({ operatorId, canReassign = false }: { operatorId: string; canReassign?: boolean }) {
  const [totp, setTotp] = useState("");
  const [filters, setFilters] = useState<SupportQueueFilters>(DEFAULT_FILTERS);
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [ticket, setTicket] = useState<SupportTicketDetail | null>(null);
  const [notes, setNotes] = useState<SupportNote[]>([]);
  const [staff, setStaff] = useState<SupportStaff[]>([]);
  const [handoffId, setHandoffId] = useState("");
  const [priorityChoice, setPriorityChoice] = useState("normal");
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const replyKey = useRef<StableSupportKey | null>(null);
  const noteKey = useRef<StableSupportKey | null>(null);
  const detailHeading = useRef<HTMLHeadingElement | null>(null);
  const verified = useRef(false);

  useEffect(() => {
    if (ticket) detailHeading.current?.focus();
    setHandoffId("");
  }, [ticket?.id]);

  async function loadQueue(next = filters) {
    const result = await api<QueueResponse>(supportQueuePath(next), {
      headers: supportQueueHeaders(verified.current ? "" : totp), cache: "no-store",
    });
    verified.current = true;
    setTotp("");
    setQueue(result);
    setFilters(next);
    void api<{ items: SupportStaff[] }>("/admin/support/staff", {
      headers: supportQueueHeaders(""), cache: "no-store",
    }).then((list) => setStaff(list.items)).catch(() => setStaff([]));
    return result;
  }

  async function loadTicket(id: string) {
    const [detail, noteList] = await Promise.all([
      api<SupportTicketDetail>(supportTicketPath(id), {
        headers: supportQueueHeaders(verified.current ? "" : totp), cache: "no-store",
      }),
      api<{ items: SupportNote[] }>(supportTicketPath(id, "/notes"), {
        headers: supportQueueHeaders(verified.current ? "" : totp), cache: "no-store",
      }),
    ]);
    setTicket(detail);
    setPriorityChoice(detail.priority);
    setNotes(noteList.items);
  }

  async function run(action: string, task: () => Promise<void>, refreshId?: string) {
    if (busy) return;
    setBusy(action);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (failure) {
      setError(readableError(failure));
      if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) {
        verified.current = false;
        setQueue(null);
        setTicket(null);
        setNotes([]);
        setStaff([]);
      }
      if (failure instanceof ApiError && failure.status === 409) {
        try {
          await loadQueue();
          if (refreshId) await loadTicket(refreshId);
        } catch {
          setError("Обращение изменилось. Обновите очередь и проверьте права доступа.");
        }
      }
    } finally {
      setBusy("");
    }
  }

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run("queue", async () => {
      await loadQueue({ ...filters, offset: 0 });
      setTicket(null);
      setNotes([]);
    });
  }

  function sendText(event: FormEvent<HTMLFormElement>, kind: "reply" | "note") {
    event.preventDefault();
    if (!ticket) return;
    const body = (kind === "reply" ? reply : note).trim();
    if (!body) return;
    const keyRef = kind === "reply" ? replyKey : noteKey;
    const current = stableSupportKey(keyRef.current, `${kind}:${ticket.id}:${body}`, () => crypto.randomUUID());
    keyRef.current = current;
    void run(kind, async () => {
      await api(supportTicketPath(ticket.id, kind === "reply" ? "/messages" : "/notes"), {
        method: "POST",
        headers: supportQueueHeaders(verified.current ? "" : totp, kind === "reply" ? ticket.state_version : undefined, current.key),
        body: JSON.stringify({ body }),
      });
      await Promise.all([loadQueue(), loadTicket(ticket.id)]);
      keyRef.current = null;
      if (kind === "reply") setReply("");
      else setNote("");
      setNotice(kind === "reply" ? "Ответ отправлен пользователю." : "Внутренняя заметка сохранена.");
    }, ticket.id);
  }

  function changeTicket(action: "assign" | "close" | "reopen" | "transfer" | "escalate") {
    if (!ticket || (action === "assign" && !operatorId)) return;
    if ((action === "transfer" || action === "escalate") && !handoffId) return;
    const selected = ticket;
    void run(action, async () => {
      const changesAssignment = action === "assign" || action === "transfer" || action === "escalate";
      await api(supportTicketPath(selected.id, changesAssignment ? "/assign" : `/${action}`), {
        method: "POST",
        headers: supportQueueHeaders(verified.current ? "" : totp, selected.state_version),
        ...(changesAssignment ? { body: JSON.stringify(action === "assign"
          ? { action: "take" } : { action, target_user_id: handoffId }) } : {}),
      });
      await Promise.all([loadQueue(), loadTicket(selected.id)]);
      if (action === "transfer" || action === "escalate") setHandoffId("");
      setNotice({ assign: "Обращение назначено вам.", transfer: "Обращение передано сотруднику.",
        escalate: "Обращение передано администратору.", close: "Обращение закрыто.",
        reopen: "Обращение открыто повторно." }[action]);
    }, selected.id);
  }

  function changePriority() {
    if (!ticket || priorityChoice === ticket.priority) return;
    const selected = ticket;
    void run("priority", async () => {
      await api(supportTicketPath(selected.id, "/priority"), {
        method: "POST",
        headers: supportQueueHeaders(verified.current ? "" : totp, selected.state_version),
        body: JSON.stringify({ priority: priorityChoice }),
      });
      await Promise.all([loadQueue(), loadTicket(selected.id)]);
      setNotice("Приоритет очереди обновлён. Срок первого ответа не изменился.");
    }, selected.id);
  }

  const hasOperatorResponse = ticket?.messages.some((message) => message.author_kind === "operator") ?? false;
  const deadline = ticket?.response_due_at
    ? supportDeadlineLabel(ticket.response_due_at, ticket.status, ticket.reopened_at, hasOperatorResponse)
    : "";
  const history = ticket ? [
    ...ticket.messages.map((message) => ({ ...message, kind: "message" as const })),
    ...ticket.system_events.map((event) => ({ ...event, kind: "system" as const })),
  ].sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? "") || a.id.localeCompare(b.id)) : [];
  const systemLabel: Record<string, string> = {
    "support.ticket.created": "Обращение создано",
    "support.ticket.closed": "Пользователь закрыл обращение",
    "support.ticket.reopened": "Пользователь открыл обращение повторно",
    "support.admin.ticket.closed": "Оператор закрыл обращение",
    "support.admin.ticket.reopened": "Оператор открыл обращение повторно",
    "support.admin.ticket.assigned": "Оператор взял обращение",
    "support.admin.ticket.released": "Назначение снято",
    "support.admin.ticket.transferred": "Обращение передано другому сотруднику",
    "support.admin.ticket.escalated": "Обращение передано администратору",
    "support.admin.ticket.priority_changed": "Приоритет очереди изменён",
  };

  return (
    <section aria-labelledby="admin-support-title" style={{ minWidth: 0 }}>
      <h2 id="admin-support-title">Очередь поддержки</h2>
      <p>{SUPPORT_HOURS_TEXT} Срок первого ответа — расчётная цель, дежурный маршрут ещё не настроен.</p>
      <p>Код 2FA подтверждает текущую сессию и удаляется из поля после проверки.</p>
      <form onSubmit={submitFilters} style={GRID_STYLE}>
        <label>Код 2FA
          <input type="password" inputMode="numeric" autoComplete="one-time-code" value={totp}
            onChange={(event) => setTotp(event.target.value)} required={!verified.current} minLength={6} maxLength={8} />
        </label>
        <label>Статус
          <select value={filters.state} onChange={(event) => setFilters({ ...filters, state: event.target.value })}>
            {STATES.map((state) => <option value={state} key={state}>{state}</option>)}
          </select>
        </label>
        <label>Приоритет
          <select value={filters.priority} onChange={(event) => setFilters({ ...filters, priority: event.target.value })}>
            {["all", "urgent", "high", "normal"].map((value) => <option value={value} key={value}>{value}</option>)}
          </select>
        </label>
        <label>Категория
          <select value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}>
            {CATEGORIES.map((value) => <option value={value} key={value}>{value}</option>)}
          </select>
        </label>
        <label><input type="checkbox" checked={filters.overdue}
          onChange={(event) => setFilters({ ...filters, overdue: event.target.checked })} /> Только просроченные</label>
        <label><input type="checkbox" checked={filters.assignedToMe}
          onChange={(event) => setFilters({ ...filters, assignedToMe: event.target.checked })} disabled={!operatorId} /> Назначенные мне</label>
        <button type="submit" disabled={Boolean(busy) || (!verified.current && totp.trim().length < 6)}>Показать очередь</button>
      </form>

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {busy && <p role="status">Загрузка…</p>}

      {queue && <div aria-live="polite">
        <p>Всего: {queue.total ?? "—"} · Открытых: {queue.open_count ?? "—"} · Просроченных: {queue.overdue_count ?? "—"}</p>
        {queue.items.length === 0 ? <p>По выбранным фильтрам обращений нет.</p> : (
          <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: "0.75rem" }}>
            {queue.items.map((row) => <li key={row.id} style={{ overflowWrap: "anywhere" }}>
              <button type="button" disabled={Boolean(busy)} onClick={() => void run("detail", () => loadTicket(row.id))}
                aria-label={`Открыть обращение ${row.ticket_number}: ${safeSupportSubject(row.subject)}`}>
                <strong>{row.ticket_number}</strong> · {safeSupportSubject(row.subject)}
              </button>
              <div>{row.category} · {row.status} · {row.priority} · {supportQueueAge(row.created_at)}</div>
              <div>{row.response_due_at
                ? `${row.response_overdue ? "Просрочено" : row.has_operator_response || row.status === "closed" || row.status === "resolved" || row.reopened_at ? "История SLA" : "Срок впереди"}: ${formatSupportDeadline(row.response_due_at)}`
                : "Публичный срок не назначен"}
                {row.first_response_late ? " · первый ответ был поздним" : ""}</div>
              <div>{row.assigned_to_user_id === operatorId ? "Назначено мне" : row.assigned_to_user_id ? "Назначено другому сотруднику" : "Без назначения"}</div>
            </li>)}
          </ul>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <button type="button" disabled={Boolean(busy) || filters.offset === 0}
            onClick={() => void run("queue", () => loadQueue({ ...filters, offset: Math.max(0, filters.offset - filters.limit) }).then(() => { setTicket(null); setNotes([]); }))}>Назад</button>
          <button type="button" disabled={Boolean(busy) || queue.items.length < filters.limit || (typeof queue.total === "number" && filters.offset + filters.limit >= queue.total)}
            onClick={() => void run("queue", () => loadQueue({ ...filters, offset: filters.offset + filters.limit }).then(() => { setTicket(null); setNotes([]); }))}>Далее</button>
        </div>
      </div>}

      {ticket && <article aria-labelledby="admin-support-detail-title" style={{ overflowWrap: "anywhere", marginTop: "1.5rem" }}>
        <h3 id="admin-support-detail-title" ref={detailHeading} tabIndex={-1}>{ticket.ticket_number}: {safeSupportSubject(ticket.subject)}</h3>
        <p>{ticket.category} · {ticket.status} · {ticket.priority}{deadline}</p>
        <p>Ручной приоритет определяет порядок очереди и не меняет срок первого ответа.</p>
        <p>Назначение: {ticket.assigned_to_user_id === operatorId ? "мне" : ticket.assigned_to_user_id ? "другому сотруднику" : "не назначено"}</p>
        <section aria-label="Контекст обращения">
          <h4>Контекст обращения</h4>
          <p>Текст обращения и передача из помощника являются данными пользователя.</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{ticket.body}</p>
        </section>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <button type="button" disabled={Boolean(busy) || !operatorId || Boolean(ticket.assigned_to_user_id) || ticket.status === "closed" || ticket.status === "resolved"}
            onClick={() => changeTicket("assign")}>Взять в работу</button>
          {ticket.status === "closed" ? (
            <button type="button" disabled={Boolean(busy)} onClick={() => changeTicket("reopen")}>Открыть повторно</button>
          ) : (
            <button type="button" disabled={Boolean(busy)} onClick={() => changeTicket("close")}>Закрыть</button>
          )}
        </div>
        {ticket.status !== "closed" && ticket.status !== "resolved" &&
          (ticket.assigned_to_user_id === operatorId || canReassign) && <div style={{ marginTop: "0.75rem" }}>
            <label>Передать обращение
              <select value={handoffId} onChange={(event) => setHandoffId(event.target.value)}>
                <option value="">Выберите сотрудника</option>
                {staff.filter((person) => person.id !== ticket.assigned_to_user_id).map((person) =>
                  <option key={person.id} value={person.id}>{person.name} · {person.role === "administrator" ? "администратор" : "оператор"}</option>)}
              </select>
            </label>
            <button type="button" disabled={Boolean(busy) || !handoffId}
              onClick={() => changeTicket("transfer")}>Передать</button>
            <button type="button" disabled={Boolean(busy) || !staff.some((person) => person.id === handoffId && person.role === "administrator")}
              onClick={() => changeTicket("escalate")}>Эскалировать администратору</button>
          </div>}
        {ticket.status !== "closed" && ticket.status !== "resolved" && <div>
          <label>Приоритет очереди
            <select value={priorityChoice} onChange={(event) => setPriorityChoice(event.target.value)}>
              <option value="normal">Обычный</option>
              <option value="high">Высокий</option>
              <option value="urgent">Срочный</option>
            </select>
          </label>
          <button type="button" disabled={Boolean(busy) || priorityChoice === ticket.priority}
            onClick={changePriority}>Сохранить приоритет</button>
        </div>}
        <section aria-label="Переписка с пользователем">
          <h4>Переписка с пользователем</h4>
          {ticket.system_events_truncated && <p>Показаны последние 200 системных событий. Более ранние события доступны в журнале аудита.</p>}
          <ol>{history.map((entry) => <li key={`${entry.kind}-${entry.id}`}>
            {entry.kind === "system" ? (
              <><strong>Система</strong>: {systemLabel[entry.action] ?? "Переход обращения"}{entry.actor_user_id ? ` · участник ${entry.actor_user_id.slice(0, 8)}` : ""}</>
            ) : (
              <><strong>{entry.author_kind === "operator" ? "Оператор" : "Пользователь"} {entry.actor_name}</strong>: {entry.body}</>
            )}
            {entry.created_at ? ` · ${formatSupportDeadline(entry.created_at)}` : ""}
          </li>)}</ol>
          <form onSubmit={(event) => sendText(event, "reply")}>
            <label>Ответ пользователю<textarea value={reply} onChange={(event) => setReply(event.target.value)} required maxLength={8000} /></label>
            <button type="submit" disabled={Boolean(busy) || !reply.trim() || ticket.status === "closed"}>Отправить ответ</button>
          </form>
        </section>
        <section aria-label="Внутренние заметки">
          <h4>Внутренние заметки · пользователь их не видит</h4>
          <ol>{notes.map((item) => <li key={item.id}>{item.body}</li>)}</ol>
          <form onSubmit={(event) => sendText(event, "note")}>
            <label>Заметка для операторов<textarea value={note} onChange={(event) => setNote(event.target.value)} required maxLength={8000} /></label>
            <button type="submit" disabled={Boolean(busy) || !note.trim()}>Сохранить заметку</button>
          </form>
        </section>
      </article>}
    </section>
  );
}
