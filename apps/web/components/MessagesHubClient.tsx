"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

type InboxItem = {
  conversation_id: string;
  request_id: string;
  request_status: string;
  booking_id: string | null;
  booking_status: string | null;
  event_title: string;
  customer_org: string;
  supplier_org: string;
  deal_path: string | null;
  can_write: boolean;
  unread_count: number;
  last_message: {
    body: string;
    kind: string;
    author_side?: "customer" | "supplier" | null;
    author_name?: string | null;
    attribution_status?: string;
    created_at?: string | null;
  } | null;
};

type ConversationMessage = {
  id: string;
  author_user_id: string | null;
  author_org_id: string | null;
  author_side: "customer" | "supplier" | null;
  author_name: string | null;
  actor_role: string | null;
  attribution_status: string;
  kind: string;
  body: string;
  created_at: string;
};

type ConversationDetail = {
  conversation_id: string;
  request_id: string;
  booking_id: string | null;
  messages: ConversationMessage[];
};

function messageAuthor(message: ConversationMessage): string {
  if (message.kind === "system") return "Букер";
  if (message.attribution_status !== "attributed") return "Участник (архив)";
  const role = message.author_side === "customer" ? "Заказчик" : "Исполнитель";
  return message.author_name ? `${role} · ${message.author_name}` : role;
}

export function MessagesHubClient({ backHref }: { backHref: string }) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [hasToken, setHasToken] = useState(false);
  const [openConversation, setOpenConversation] = useState<ConversationDetail | null>(null);
  const [threadLoading, setThreadLoading] = useState<string | null>(null);
  const [threadError, setThreadError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendAttempt, setSendAttempt] = useState<{ body: string; key: string } | null>(null);

  useEffect(() => {
    const authenticated = Boolean(getToken());
    setHasToken(authenticated);
    setAuthReady(true);
    if (!authenticated) {
      setReady(true);
      return;
    }
    let cancelled = false;
    api<{ items: InboxItem[] }>("/messages/inbox")
      .then((data) => {
        if (!cancelled) {
          setItems(data.items || []);
          setError("");
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Не удалось загрузить сообщения");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function openThread(item: InboxItem) {
    if (openConversation?.conversation_id === item.conversation_id) {
      setOpenConversation(null);
      setThreadError("");
      setDraft("");
      setSendAttempt(null);
      return;
    }
    setThreadLoading(item.conversation_id);
    setThreadError("");
    setDraft("");
    setSendAttempt(null);
    try {
      const detail = await api<ConversationDetail>(`/requests/${item.request_id}/conversation`);
      setOpenConversation(detail);
      try {
        await api(`/conversations/${item.conversation_id}/read`, { method: "POST" });
        setItems((current) =>
          current.map((candidate) =>
            candidate.conversation_id === item.conversation_id
              ? { ...candidate, unread_count: 0 }
              : candidate,
          ),
        );
      } catch (e) {
        setThreadError(e instanceof ApiError ? e.message : "Не удалось отметить переписку прочитанной");
      }
    } catch (e) {
      setOpenConversation(null);
      setThreadError(e instanceof ApiError ? e.message : "Не удалось открыть переписку");
    } finally {
      setThreadLoading(null);
    }
  }

  async function sendMessage(item: InboxItem) {
    const body = draft.trim();
    if (!body || sending || !item.can_write) return;
    const attempt = sendAttempt?.body === body ? sendAttempt : { body, key: crypto.randomUUID() };
    setSendAttempt(attempt);
    setSending(true);
    setThreadError("");
    try {
      await api(`/requests/${item.request_id}/messages`, {
        method: "POST",
        body: JSON.stringify({ body, idempotency_key: attempt.key }),
      });
      const detail = await api<ConversationDetail>(`/requests/${item.request_id}/conversation`);
      setOpenConversation(detail);
      setDraft("");
      setSendAttempt(null);
      setItems((current) =>
        current.map((candidate) =>
          candidate.conversation_id === item.conversation_id
            ? {
                ...candidate,
                last_message: detail.messages.length
                  ? detail.messages[detail.messages.length - 1]
                  : candidate.last_message,
                unread_count: 0,
              }
            : candidate,
        ),
      );
    } catch (e) {
      setThreadError(e instanceof ApiError ? e.message : "Не удалось отправить сообщение");
    } finally {
      setSending(false);
    }
  }

  if (!authReady) {
    return (
      <main>
        <p className="kicker">Центр сообщений</p>
        <h1>Сообщения</h1>
        <p>Загрузка…</p>
      </main>
    );
  }

  if (!hasToken) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Сообщения</h1>
        <p>
          <Link className="btn" href={loginHref(backHref)}>
            Войти
          </Link>
        </p>
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Центр сообщений</p>
      <h1>Сообщения</h1>
      <p className="timeline">Переписки по заявкам и сделкам. Без чужих диалогов.</p>
      <p>
        <Link className="btn secondary" href={backHref}>
          К кабинету
        </Link>
      </p>
      {!ready ? <p>Загрузка…</p> : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {ready && !error && items.length === 0 ? (
        <article className="card empty" style={{ marginTop: 16 }}>
          <h2>Пока тихо</h2>
          <p>Когда появится заявка с перепиской, она будет здесь.</p>
        </article>
      ) : null}
      <div className="grid" style={{ marginTop: 16 }}>
        {items.map((it) => (
          <article className="card" key={it.conversation_id}>
            <h2>{it.event_title || "Заявка"}</h2>
            <p className="timeline">
              {it.customer_org} ↔ {it.supplier_org} · {it.booking_status || it.request_status}
            </p>
            {it.last_message ? (
              <p>
                {it.last_message.kind === "system"
                  ? "Букер"
                  : it.last_message.attribution_status === "attributed"
                    ? it.last_message.author_side === "customer"
                      ? "Заказчик"
                      : "Исполнитель"
                    : "Участник (архив)"}
                : {it.last_message.body}
              </p>
            ) : (
              <p>Нет сообщений</p>
            )}
            {it.unread_count > 0 ? <p className="timeline">Новых: {it.unread_count}</p> : null}
            {it.deal_path ? (
              <Link className="btn" href={it.deal_path}>
                Открыть Deal Room
              </Link>
            ) : (
              <>
                <button
                  type="button"
                  className="secondary"
                  aria-expanded={openConversation?.conversation_id === it.conversation_id}
                  onClick={() => void openThread(it)}
                  disabled={threadLoading === it.conversation_id}
                >
                  {threadLoading === it.conversation_id
                    ? "Открываем…"
                    : openConversation?.conversation_id === it.conversation_id
                      ? "Свернуть переписку"
                      : "Открыть переписку"}
                </button>
                <p className="timeline">Deal Room откроется после предложения.</p>
              </>
            )}
            {openConversation?.conversation_id === it.conversation_id ? (
              <section aria-label={`Переписка: ${it.event_title || "Заявка"}`}>
                {openConversation.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`msg ${message.kind === "system" ? "system" : "chat"}`}
                  >
                    <strong>{messageAuthor(message)}:</strong>{" "}
                    {message.body}
                    <div className="timeline" style={{ textAlign: "right" }}>
                      {new Date(message.created_at).toLocaleString("ru-RU")}
                    </div>
                  </div>
                ))}
                {it.can_write ? (
                  <form
                    className="chat-compose"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void sendMessage(it);
                    }}
                  >
                    <textarea
                      value={draft}
                      onChange={(event) => {
                        setDraft(event.target.value);
                        setSendAttempt(null);
                      }}
                      minLength={1}
                      maxLength={8000}
                      placeholder="Напишите сообщение по заявке"
                      aria-label="Сообщение по заявке"
                      disabled={sending}
                    />
                    <button type="submit" disabled={sending || !draft.trim()}>
                      {sending ? "Отправляем…" : "Отправить"}
                    </button>
                  </form>
                ) : (
                  <p className="timeline">Только просмотр: для ответа нужна роль менеджера.</p>
                )}
                {threadError ? <p style={{ color: "var(--danger)" }}>{threadError}</p> : null}
              </section>
            ) : null}
          </article>
        ))}
      </div>
    </main>
  );
}
