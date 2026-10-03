"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError, getActiveOrg, getToken } from "@/lib/api";
import Link from "next/link";
import { loginHref } from "@/lib/next";
import { supportDeadlineLabel, SUPPORT_HOURS_TEXT, SUPPORT_TARGET_TEXT } from "@/lib/supportSla";

type Ticket = {
  id: string;
  ticket_number: string;
  category: string;
  subject: string;
  status: string;
  priority?: string;
  response_due_at?: string | null;
  reopened_at?: string | null;
};

type TicketMessage = {
  id: string;
  author_kind: "user" | "operator";
  body: string;
  created_at: string;
};

type TicketDetail = Ticket & {
  body: string;
  state_version: number;
  messages: TicketMessage[];
};

type Exchange = {
  id: string;
  user_message: string;
  assistant_message: string;
  intent: string;
  outcome: string;
  needs_human: boolean;
  source_ids: string[];
  created_at: string;
  feedback?: { id: string; rating: "helpful" | "not_helpful" } | null;
};

type AssistantSession = {
  id: string;
  status: string;
  ticket_id?: string;
  related_type?: string | null;
  related_id?: string | null;
  messages?: Exchange[];
};

type EscalatedTicket = {
  id: string;
  ticket_number: string;
  status: string;
  category: string;
  subject: string;
};

type StableRequestKey = {
  signature: string;
  key: string;
};

const CATEGORIES = [
  "profile",
  "brief",
  "message",
  "review",
  "media",
  "payment",
  "incident",
  "technical",
  "other",
];

function assistantSessionStorageKey(userId: string, bookingId: string | null): string {
  const base = `booker.support.assistantSession.${userId}.${getActiveOrg() || "personal"}`;
  return bookingId ? `${base}.booking.${bookingId}` : base;
}

function legacyAssistantSessionStorageKey(): string {
  return `booker.support.assistantSession.${getActiveOrg() || "personal"}`;
}

function SupportInner({ bookingId }: { bookingId: string | null }) {
  const [authReady, setAuthReady] = useState(false);
  const [hasToken, setHasToken] = useState(false);
  const [items, setItems] = useState<Ticket[]>([]);
  const [humanError, setHumanError] = useState("");
  const [category, setCategory] = useState("other");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [humanBusy, setHumanBusy] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<TicketDetail | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [ticketBusy, setTicketBusy] = useState<"loading" | "reply" | "state" | null>(null);
  const [assistantSession, setAssistantSession] = useState<AssistantSession | null>(null);
  const [assistantStorageKey, setAssistantStorageKey] = useState<string | null>(null);
  const [assistantMessages, setAssistantMessages] = useState<Exchange[]>([]);
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantError, setAssistantError] = useState("");
  const [assistantBusy, setAssistantBusy] = useState<"sending" | "escalating" | null>(null);
  const [feedbackBusyId, setFeedbackBusyId] = useState<string | null>(null);
  const [feedbackComments, setFeedbackComments] = useState<Record<string, string>>({});
  const [feedbackErrors, setFeedbackErrors] = useState<Record<string, string>>({});
  const [escalatedTicket, setEscalatedTicket] = useState<EscalatedTicket | null>(null);
  const humanRequestKey = useRef<StableRequestKey | null>(null);
  const sessionRequestKey = useRef<StableRequestKey | null>(null);
  const messageRequestKey = useRef<StableRequestKey | null>(null);
  const escalationRequestKey = useRef<StableRequestKey | null>(null);
  const replyRequestKey = useRef<StableRequestKey | null>(null);
  const feedbackRequestInFlight = useRef<string | null>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement | null>(null);
  const relatedBookingId = useRef(bookingId);

  function stableKey(ref: { current: StableRequestKey | null }, signature: string): string {
    if (!ref.current || ref.current.signature !== signature) {
      ref.current = { signature, key: crypto.randomUUID() };
    }
    return ref.current.key;
  }

  async function load() {
    if (!getToken()) return;
    try {
      const data = await api<{ items: Ticket[] }>("/support/tickets");
      setItems(data.items || []);
      setHumanError("");
    } catch (e) {
      setHumanError(e instanceof ApiError ? e.message : "Не удалось загрузить обращения");
    }
  }

  useEffect(() => {
    const authenticated = Boolean(getToken());
    setHasToken(authenticated);
    setAuthReady(true);
    if (authenticated) {
      void load();
      void (async () => {
        try {
          const me = await api<{ id: string }>("/me");
          const key = assistantSessionStorageKey(me.id, relatedBookingId.current);
          setAssistantStorageKey(key);
          await restoreAssistantSession(key);
        } catch (err) {
          setAssistantError(
            err instanceof ApiError ? err.message : "Не удалось определить пользователя",
          );
        }
      })();
    }
  }, []);

  async function restoreAssistantSession(storageKey: string) {
    const legacyKey = legacyAssistantSessionStorageKey();
    const ownSessionId = localStorage.getItem(storageKey);
    const sessionId = ownSessionId || (relatedBookingId.current ? null : localStorage.getItem(legacyKey));
    if (!sessionId) return;
    try {
      const session = await api<AssistantSession>(
        `/support/assistant/sessions/${sessionId}`,
      );
      if (relatedBookingId.current && (
        session.related_type !== "booking" || session.related_id !== relatedBookingId.current
      )) {
        localStorage.removeItem(storageKey);
        return;
      }
      setAssistantSession(session);
      setAssistantMessages(session.messages || []);
      if (!ownSessionId) {
        localStorage.setItem(storageKey, session.id);
        localStorage.removeItem(legacyKey);
      }
      if (session.ticket_id) {
        const ticket = await api<TicketDetail>(`/support/tickets/${session.ticket_id}`);
        setSelectedTicket(ticket);
        setEscalatedTicket(ticket);
      }
    } catch (err) {
      if (ownSessionId) localStorage.removeItem(storageKey);
      if (!(err instanceof ApiError && err.status === 404)) {
        setAssistantError(
          err instanceof ApiError ? err.message : "Не удалось восстановить диалог",
        );
      }
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!getToken()) {
      setHumanError("Нужен вход");
      return;
    }
    if (subject.trim().length < 3 || body.trim().length < 3) {
      setHumanError("Введите тему и описание не короче трёх символов");
      return;
    }
    const payload = {
      organization_id: getActiveOrg() || undefined,
      category,
      subject,
      body,
    };
    const requestKey = stableKey(humanRequestKey, JSON.stringify(payload));
    setHumanBusy(true);
    setHumanError("");
    try {
      const created = await api<Ticket>("/support/tickets", {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify(payload),
      });
      humanRequestKey.current = null;
      setSubject("");
      setBody("");
      await load();
      await loadTicket(created.id);
    } catch (err) {
      setHumanError(err instanceof ApiError ? err.message : "Не удалось создать обращение");
    } finally {
      setHumanBusy(false);
    }
  }

  async function loadTicket(ticketId: string) {
    setTicketBusy("loading");
    setHumanError("");
    try {
      const detail = await api<TicketDetail>(`/support/tickets/${ticketId}`);
      setSelectedTicket(detail);
    } catch (err) {
      setHumanError(err instanceof ApiError ? err.message : "Не удалось открыть обращение");
    } finally {
      setTicketBusy(null);
    }
  }

  async function replyToTicket(e: FormEvent) {
    e.preventDefault();
    if (!selectedTicket || selectedTicket.status === "closed") return;
    const message = replyBody.trim();
    if (!message) return;
    const requestKey = stableKey(
      replyRequestKey,
      `${selectedTicket.id}:${message}`,
    );
    setTicketBusy("reply");
    setHumanError("");
    try {
      await api(`/support/tickets/${selectedTicket.id}/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify({ body: message }),
      });
      replyRequestKey.current = null;
      setReplyBody("");
      await loadTicket(selectedTicket.id);
      await load();
    } catch (err) {
      setHumanError(err instanceof ApiError ? err.message : "Не удалось отправить сообщение");
    } finally {
      setTicketBusy(null);
    }
  }

  async function changeTicketState(action: "close" | "reopen") {
    if (!selectedTicket) return;
    setTicketBusy("state");
    setHumanError("");
    try {
      await api(`/support/tickets/${selectedTicket.id}/${action}`, {
        method: "POST",
        headers: { "If-Match": String(selectedTicket.state_version) },
      });
      await loadTicket(selectedTicket.id);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          setSelectedTicket(await api<TicketDetail>(`/support/tickets/${selectedTicket.id}`));
        } catch {
          // Keep the server error visible; the user can reopen the ticket list.
        }
      }
      setHumanError(err instanceof ApiError ? err.message : "Не удалось изменить обращение");
    } finally {
      setTicketBusy(null);
    }
  }

  async function sendAssistantMessage(e: FormEvent) {
    e.preventDefault();
    if (!assistantStorageKey) {
      setAssistantError("Не удалось определить пользователя. Обновите страницу.");
      return;
    }
    if (assistantSession && assistantSession.status !== "active") return;
    const message = assistantInput.trim();
    if (message.length < 3) {
      setAssistantError("Введите не менее трёх символов");
      return;
    }
    if (assistantBusy) return;
    setAssistantBusy("sending");
    setAssistantError("");
    try {
      let session = assistantSession;
      if (!session) {
        const organizationId = getActiveOrg() || undefined;
        const sessionPayload = {
          organization_id: organizationId,
          ...(relatedBookingId.current
            ? { related_type: "booking", related_id: relatedBookingId.current }
            : {}),
        };
        const createSignature = JSON.stringify(sessionPayload);
        const createKey = stableKey(sessionRequestKey, createSignature);
        session = await api<AssistantSession>("/support/assistant/sessions", {
          method: "POST",
          headers: { "Idempotency-Key": createKey },
          body: JSON.stringify(sessionPayload),
        });
        sessionRequestKey.current = null;
        setAssistantSession(session);
        setAssistantMessages(session.messages || []);
        localStorage.setItem(assistantStorageKey, session.id);
      }

      const messageKey = stableKey(messageRequestKey, `${session.id}:${message}`);
      const exchange = await api<Exchange>(
        `/support/assistant/sessions/${session.id}/messages`,
        {
          method: "POST",
          headers: { "Idempotency-Key": messageKey },
          body: JSON.stringify({ message }),
        },
      );
      messageRequestKey.current = null;
      setAssistantMessages((current) => {
        const withoutReplay = current.filter((item) => item.id !== exchange.id);
        return [...withoutReplay, exchange];
      });
      setAssistantInput("");
    } catch (err) {
      setAssistantError(err instanceof ApiError ? err.message : "Не удалось получить ответ помощника");
    } finally {
      setAssistantBusy(null);
    }
  }

  async function escalateAssistantSession() {
    if (!assistantSession || assistantBusy) return;
    const reasonCode = "user_requested_human";
    const requestKey = stableKey(
      escalationRequestKey,
      `${assistantSession.id}:${reasonCode}`,
    );
    setAssistantBusy("escalating");
    setAssistantError("");
    try {
      const result = await api<{
        session_id: string;
        status: string;
        ticket: EscalatedTicket;
      }>(`/support/assistant/sessions/${assistantSession.id}/escalate`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify({ reason_code: reasonCode }),
      });
      escalationRequestKey.current = null;
      setAssistantSession((current) =>
        current
          ? { ...current, status: result.status, ticket_id: result.ticket.id }
          : current,
      );
      setEscalatedTicket(result.ticket);
      await loadTicket(result.ticket.id);
      await load();
    } catch (err) {
      setAssistantError(err instanceof ApiError ? err.message : "Не удалось передать обращение");
    } finally {
      setAssistantBusy(null);
    }
  }

  function startNewAssistantSession() {
    if (!assistantStorageKey || assistantBusy || feedbackBusyId) return;
    if (
      assistantInput.trim() &&
      !window.confirm("Несохранённый текст старого диалога исчезнет. Начать новый вопрос?")
    ) {
      return;
    }
    localStorage.removeItem(assistantStorageKey);
    setAssistantSession(null);
    setAssistantMessages([]);
    setAssistantInput("");
    setAssistantError("");
    setEscalatedTicket(null);
    setFeedbackComments({});
    setFeedbackErrors({});
    sessionRequestKey.current = null;
    messageRequestKey.current = null;
    escalationRequestKey.current = null;
    requestAnimationFrame(() => assistantInputRef.current?.focus());
  }

  async function rateAssistantExchange(
    exchange: Exchange,
    rating: "helpful" | "not_helpful",
  ) {
    if (exchange.feedback || feedbackRequestInFlight.current) return;
    feedbackRequestInFlight.current = exchange.id;
    setFeedbackBusyId(exchange.id);
    setFeedbackErrors((current) => ({ ...current, [exchange.id]: "" }));
    try {
      const feedback = await api<{ id: string; rating: "helpful" | "not_helpful" }>(
        `/support/assistant/exchanges/${exchange.id}/feedback`,
        {
          method: "POST",
          body: JSON.stringify({ rating, comment: feedbackComments[exchange.id] || "" }),
        },
      );
      setAssistantMessages((current) =>
        current.map((item) => (item.id === exchange.id ? { ...item, feedback } : item)),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && assistantSession) {
        try {
          const current = await api<AssistantSession>(
            `/support/assistant/sessions/${assistantSession.id}`,
          );
          setAssistantMessages(current.messages || []);
        } catch {
          // Keep the feedback error visible if the session can no longer be read.
        }
      }
      setFeedbackErrors((current) => ({
        ...current,
        [exchange.id]: err instanceof ApiError ? err.message : "Не удалось сохранить оценку",
      }));
    } finally {
      feedbackRequestInFlight.current = null;
      setFeedbackBusyId(null);
    }
  }

  if (!authReady) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Поддержка</h1>
        <p>Загружаем…</p>
      </main>
    );
  }

  if (!hasToken) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Поддержка</h1>
        <p>
          <Link className="btn" href={loginHref("/support")}>
            Войти
          </Link>
        </p>
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Букер</p>
      <h1>Поддержка и жалобы</h1>
      <p className="timeline">{SUPPORT_HOURS_TEXT} {SUPPORT_TARGET_TEXT}</p>
      <section
        className="card"
        style={{ marginTop: 16, display: "grid", gap: 12 }}
        aria-busy={assistantBusy !== null}
      >
        <div>
          <h2 style={{ marginTop: 0 }}>Помощник Букера</h2>
          <p className="timeline" style={{ marginBottom: 0 }}>
            Помощник объясняет интерфейс и следующие шаги. Он не меняет бронирование, оплату или
            статусы и не обещает сроки.
          </p>
          {relatedBookingId.current ? (
            <p className="timeline">
              Вопрос связан с открытой вами бронью. <Link href={`/deals/${relatedBookingId.current}`}>Вернуться в Deal Room</Link>
            </p>
          ) : null}
        </div>
        {assistantMessages.length === 0 ? (
          <p>Опишите вопрос — сессия создастся при первой отправке.</p>
        ) : null}
        {assistantMessages.map((exchange, index) => (
          <div
            key={exchange.id}
            role="group"
            aria-label={`Вопрос и ответ ${index + 1}`}
            style={{ display: "grid", gap: 8 }}
          >
            <div className="card" style={{ padding: 12 }}>
              <strong>Вы:</strong> {exchange.user_message}
            </div>
            <div className="card" style={{ padding: 12 }}>
              <strong>Помощник:</strong> {exchange.assistant_message}
              {exchange.needs_human ? (
                <p className="timeline" style={{ marginBottom: 0 }}>
                  Для продолжения нужен человек.
                </p>
              ) : null}
              {exchange.source_ids.length > 0 ? (
                <p className="timeline" style={{ marginBottom: 0 }}>
                  Использовано источников: {exchange.source_ids.length}
                </p>
              ) : null}
              {exchange.feedback ? (
                <p role="status" style={{ marginBottom: 0 }}>
                  Оценка сохранена: {exchange.feedback.rating === "helpful" ? "полезно" : "не помогло"}.
                </p>
              ) : (
                <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                  <details>
                    <summary>Добавить комментарий к оценке</summary>
                    <label htmlFor={`support-feedback-${exchange.id}`}>Комментарий (необязательно)</label>
                    <textarea
                      id={`support-feedback-${exchange.id}`}
                      rows={2}
                      maxLength={1000}
                      value={feedbackComments[exchange.id] || ""}
                      onChange={(e) =>
                        setFeedbackComments((current) => ({
                          ...current,
                          [exchange.id]: e.target.value,
                        }))
                      }
                      disabled={feedbackBusyId !== null}
                    />
                  </details>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    <button
                      className="btn"
                      type="button"
                      aria-label={`Ответ ${index + 1}: полезно`}
                      disabled={feedbackBusyId !== null}
                      onClick={() => void rateAssistantExchange(exchange, "helpful")}
                    >
                      Полезно
                    </button>
                    <button
                      className="btn"
                      type="button"
                      aria-label={`Ответ ${index + 1}: не помогло`}
                      disabled={feedbackBusyId !== null}
                      onClick={() => void rateAssistantExchange(exchange, "not_helpful")}
                    >
                      Не помогло
                    </button>
                  </div>
                  {feedbackBusyId === exchange.id ? <p role="status">Сохраняем оценку…</p> : null}
                  {feedbackErrors[exchange.id] ? (
                    <p role="alert" style={{ color: "var(--danger)" }}>
                      {feedbackErrors[exchange.id]}
                    </p>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        ))}
        <form onSubmit={sendAssistantMessage} style={{ display: "grid", gap: 8 }}>
          <label htmlFor="support-assistant-message">Сообщение помощнику</label>
          <textarea
            id="support-assistant-message"
            ref={assistantInputRef}
            value={assistantInput}
            onChange={(e) => setAssistantInput(e.target.value)}
            rows={3}
            maxLength={4000}
            minLength={3}
            disabled={
              !assistantStorageKey ||
              assistantBusy !== null ||
              (assistantSession !== null && assistantSession.status !== "active")
            }
            required
          />
          <button
            className="btn"
            type="submit"
            disabled={
              assistantBusy !== null ||
              !assistantStorageKey ||
              !assistantInput.trim() ||
              (assistantSession !== null && assistantSession.status !== "active")
            }
          >
            {assistantBusy === "sending" ? "Отправляем…" : "Спросить помощника"}
          </button>
        </form>
        {assistantSession ? (
          <div>
            <button
              className="btn"
              type="button"
              onClick={() => void escalateAssistantSession()}
              disabled={
                assistantBusy !== null ||
                Boolean(escalatedTicket) ||
                assistantSession.status !== "active" ||
                assistantMessages.length === 0
              }
            >
              {assistantBusy === "escalating" ? "Передаём…" : "Передать человеку"}
            </button>
          </div>
        ) : null}
        {escalatedTicket ? (
          <div>
            <p role="status">
              Передано человеку: {escalatedTicket.ticket_number} · {escalatedTicket.status} —{" "}
              {escalatedTicket.subject}
            </p>
            <p className="timeline">
              По этому вопросу отвечайте в обращении ниже. Новый вопрос помощнику создаст отдельный диалог;
              он не попадёт оператору, пока вы не нажмёте «Передать человеку».
            </p>
            <a className="btn" href="#support-human-ticket">Перейти к обращению</a>{" "}
            <button
              className="btn"
              type="button"
              onClick={startNewAssistantSession}
              disabled={!assistantStorageKey || assistantBusy !== null || feedbackBusyId !== null}
            >
              Новый вопрос помощнику
            </button>
          </div>
        ) : null}
        <div aria-live="polite">
          {assistantBusy === "sending" ? <p>Помощник готовит ответ.</p> : null}
          {assistantBusy === "escalating" ? <p>Создаём человеческое обращение.</p> : null}
        </div>
        {assistantError ? (
          <p role="alert" style={{ color: "var(--danger)" }}>
            {assistantError}
          </p>
        ) : null}
      </section>
      <h2 style={{ marginTop: 24 }}>Человеческое обращение</h2>
      {humanError ? (
        <p role="alert" style={{ color: "var(--danger)" }}>
          {humanError}
        </p>
      ) : null}
      <form
        onSubmit={onSubmit}
        className="card"
        style={{ marginTop: 16, display: "grid", gap: 12 }}
        aria-busy={humanBusy}
      >
        <label>
          Категория
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Тема
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            required
            minLength={3}
            maxLength={255}
          />
        </label>
        <label>
          Описание
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
            minLength={3}
            maxLength={8000}
            rows={4}
          />
        </label>
        <button className="btn" type="submit" disabled={humanBusy}>
          {humanBusy ? "Отправляем…" : "Отправить обращение"}
        </button>
      </form>
      <section style={{ marginTop: 24 }}>
        <h2>Мои обращения</h2>
        {items.length === 0 ? <p>Пока пусто.</p> : null}
        <ul>
          {items.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => void loadTicket(t.id)}
                disabled={ticketBusy !== null}
                style={{ textAlign: "left" }}
              >
                {t.ticket_number} · {t.priority === "normal" || !t.priority ? t.category : `${t.priority} · ${t.category}`} · {t.status} — {t.subject}
              </button>
            </li>
          ))}
        </ul>
      </section>
      {selectedTicket ? (
        <section
          id="support-human-ticket"
          className="card"
          style={{ marginTop: 24, display: "grid", gap: 12 }}
        >
          <div>
            <p className="kicker">{selectedTicket.ticket_number}</p>
            <h2 style={{ marginTop: 0 }}>{selectedTicket.subject}</h2>
            <p className="timeline">
              {selectedTicket.priority && selectedTicket.priority !== "normal"
                ? `${selectedTicket.priority} · `
                : ""}
              {selectedTicket.category} · {selectedTicket.status}
              {selectedTicket.response_due_at
                ? supportDeadlineLabel(selectedTicket.response_due_at,
                    selectedTicket.status, selectedTicket.reopened_at,
                    selectedTicket.messages.some((message) => message.author_kind === "operator"))
                : ""}
            </p>
          </div>
          <div aria-live="polite" style={{ display: "grid", gap: 8 }}>
            {selectedTicket.messages.map((message) => (
              <div className="card" key={message.id} style={{ padding: 12 }}>
                <strong>{message.author_kind === "operator" ? "Поддержка" : "Вы"}:</strong>{" "}
                {message.body}
              </div>
            ))}
          </div>
          {selectedTicket.status === "closed" ? (
            <button
              className="btn"
              type="button"
              disabled={ticketBusy !== null}
              onClick={() => void changeTicketState("reopen")}
            >
              {ticketBusy === "state" ? "Открываем…" : "Открыть повторно"}
            </button>
          ) : (
            <>
              <form onSubmit={replyToTicket} style={{ display: "grid", gap: 8 }}>
                <label htmlFor="support-ticket-reply">Ответ в поддержку</label>
                <p className="timeline" style={{ margin: 0 }}>
                  Сообщение получит команда Букера; контрагент его не увидит.
                </p>
                <textarea
                  id="support-ticket-reply"
                  value={replyBody}
                  onChange={(event) => setReplyBody(event.target.value)}
                  rows={3}
                  maxLength={8000}
                  disabled={ticketBusy !== null}
                  required
                />
                <button
                  className="btn"
                  type="submit"
                  disabled={ticketBusy !== null || !replyBody.trim()}
                >
                  {ticketBusy === "reply" ? "Отправляем…" : "Отправить сообщение"}
                </button>
              </form>
              <button
                type="button"
                onClick={() => void changeTicketState("close")}
                disabled={ticketBusy !== null}
              >
                {ticketBusy === "state" ? "Закрываем…" : "Закрыть обращение"}
              </button>
            </>
          )}
        </section>
      ) : null}
    </main>
  );
}

function SupportWithBookingContext() {
  const requestedBooking = useSearchParams().get("booking");
  const bookingId = requestedBooking && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(requestedBooking)
    ? requestedBooking.toLowerCase() : null;
  return <SupportInner key={bookingId ?? "general"} bookingId={bookingId} />;
}

export default function SupportPage() {
  return <Suspense fallback={<main><p>Загрузка поддержки…</p></main>}><SupportWithBookingContext /></Suspense>;
}
