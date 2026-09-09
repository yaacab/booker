"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

type InboxItem = {
  booking_id: string;
  booking_status: string;
  event_title: string;
  customer_org: string;
  supplier_org: string;
  deal_path: string;
  last_message: { body: string; kind: string; created_at?: string | null } | null;
};

export function MessagesHubClient({ backHref }: { backHref: string }) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
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

  if (!getToken()) {
    return (
      <main className="messages-v3">
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
    <main className="messages-v3">
      <div className="messages-v3-head">
        <div>
          <p className="kicker">Центр сообщений</p>
          <h1>Сообщения</h1>
          <p className="timeline">Переписки по сделкам. Без спама и без чужих deal room.</p>
        </div>
        <Link className="btn secondary" href={backHref}>
          К кабинету
        </Link>
      </div>
      {!ready ? <p>Загрузка…</p> : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {ready && !error && items.length === 0 ? (
        <article className="card empty messages-v3-empty">
          <h2>Пока тихо</h2>
          <p>Когда появится сделка с перепиской, она будет здесь.</p>
        </article>
      ) : null}
      <div className="messages-v3-list">
        {items.map((it) => (
          <article className="card messages-v3-card" key={it.booking_id}>
            <div className="messages-v3-card-top">
              <div>
                <p className="kicker">{it.booking_status}</p>
                <h2>{it.event_title || "Сделка"}</h2>
              </div>
              <span className="messages-v3-dot" aria-hidden />
            </div>
            <p className="timeline">
              {it.customer_org} ↔ {it.supplier_org}
            </p>
            <div className="messages-v3-preview">
              {it.last_message ? <p>{it.last_message.body}</p> : <p>Нет сообщений</p>}
            </div>
            <Link className="btn" href={it.deal_path}>
              Открыть Deal Room
            </Link>
          </article>
        ))}
      </div>
    </main>
  );
}
