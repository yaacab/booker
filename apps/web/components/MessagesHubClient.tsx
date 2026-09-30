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
      <p className="timeline">Все обсуждения и договорённости по вашим событиям.</p>
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
          <p>Когда появится сделка с перепиской, она будет здесь.</p>
        </article>
      ) : null}
      <div className="inbox-list" style={{ marginTop: 16 }}>
        {items.map((it) => (
          <article className="card inbox-row" key={it.booking_id}>
            <h2>{it.event_title || "Сделка"}</h2>
            <p className="timeline">
              {it.customer_org} ↔ {it.supplier_org} · {it.booking_status}
            </p>
            {it.last_message ? <p>{it.last_message.body}</p> : <p>Нет сообщений</p>}
            <Link className="btn" href={it.deal_path}>
              Открыть переписку
            </Link>
          </article>
        ))}
      </div>
    </main>
  );
}
