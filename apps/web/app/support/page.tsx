"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, getActiveOrg, getToken } from "@/lib/api";
import Link from "next/link";
import { loginHref } from "@/lib/next";

type Ticket = {
  id: string;
  ticket_number: string;
  category: string;
  subject: string;
  status: string;
};

const CATEGORIES = [
  "profile",
  "brief",
  "message",
  "review",
  "media",
  "payment",
  "technical",
  "other",
];

export default function SupportPage() {
  const [items, setItems] = useState<Ticket[]>([]);
  const [error, setError] = useState("");
  const [category, setCategory] = useState("other");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!getToken()) return;
    try {
      const data = await api<{ items: Ticket[] }>("/support/tickets");
      setItems(data.items || []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить обращения");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!getToken()) {
      setError("Нужен вход");
      return;
    }
    setBusy(true);
    try {
      await api("/support/tickets", {
        method: "POST",
        body: JSON.stringify({
          organization_id: getActiveOrg() || undefined,
          category,
          subject,
          body,
        }),
      });
      setSubject("");
      setBody("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать обращение");
    } finally {
      setBusy(false);
    }
  }

  if (!getToken()) {
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
      <p className="timeline">Человеческая эскалация. Сроки ответа не обещаем без реального графика.</p>
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      <form onSubmit={onSubmit} className="card" style={{ marginTop: 16, display: "grid", gap: 12 }}>
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
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required minLength={3} />
        </label>
        <label>
          Описание
          <textarea value={body} onChange={(e) => setBody(e.target.value)} required minLength={3} rows={4} />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Отправить обращение
        </button>
      </form>
      <section style={{ marginTop: 24 }}>
        <h2>Мои обращения</h2>
        {items.length === 0 ? <p>Пока пусто.</p> : null}
        <ul>
          {items.map((t) => (
            <li key={t.id}>
              {t.ticket_number} · {t.category} · {t.status} — {t.subject}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
