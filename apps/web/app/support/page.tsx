"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, getActiveOrg, getToken } from "@/lib/api";
import Link from "next/link";
import { loginHref } from "@/lib/next";
import { ReferencePuzzleStrip } from "@/components/ReferencePuzzleStrip";

type Ticket = {
  id: string;
  ticket_number: string;
  category: string;
  subject: string;
  status: string;
};

const CATEGORIES: Record<string, string> = {
  profile: "Профиль", brief: "Бриф и заявка", message: "Сообщения", review: "Отзыв",
  media: "Фото и материалы", payment: "Оплата", technical: "Технический вопрос", other: "Другой вопрос",
};
const STATUS: Record<string, string> = { open: "Открыто", new: "Новое", in_progress: "В работе", resolved: "Решено", closed: "Закрыто" };

export default function SupportPage() {
  const [items, setItems] = useState<Ticket[]>([]);
  const [error, setError] = useState("");
  const [category, setCategory] = useState("other");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [sent, setSent] = useState(false);

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
    setAuthed(Boolean(getToken()));
    void load();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!getToken()) {
      setError("Нужен вход");
      return;
    }
    setBusy(true);
    setSent(false);
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
      setSent(true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать обращение");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="reference-information support-reference">
      <header className="information-heading"><p className="kicker">На связи с вами</p>
      <h1>Поддержка</h1><h2>Мы рядом, чтобы помочь.</h2>
      <p>Расскажите, что случилось. Вопрос о профиле, заявке или вашем событии — начнём с деталей.</p></header>
      <ReferencePuzzleStrip />
      {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
      {sent ? <p role="status" className="support-notice">Обращение отправлено. Оно появится в списке ниже.</p> : null}
      {authed ? <form onSubmit={onSubmit} className="card support-form">
        <h2>Отправить запрос</h2>
        <div className="information-form-row">
        <label>
          Категория
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {Object.entries(CATEGORIES).map(([c, label]) => (
              <option key={c} value={c}>
                {label}
              </option>
            ))}
          </select>
        </label>
        </div>
        <label>
          Тема
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required minLength={3} />
        </label>
        <label>
          Описание
          <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Опишите вопрос или ситуацию. Не указывайте пароли и коды подтверждения." required minLength={3} rows={5} />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Отправляем…" : "Отправить обращение →"}
        </button>
      </form> : <section className="card support-signin"><div><h2>Написать в поддержку</h2><p>Войдите, чтобы отправить обращение и видеть его статус в кабинете.</p></div><Link className="btn" href={loginHref("/support")}>Войти и написать →</Link></section>}
      {authed && <section className="support-tickets">
        <h2>Мои обращения</h2>
        {items.length === 0 ? <p className="card">Здесь появятся ваши обращения и их статусы.</p> : null}
        <ul className="support-ticket-list">
          {items.map((t) => (
            <li key={t.id}>
              <span className="support-ticket-number">{t.ticket_number}</span><strong>{t.subject}</strong><span>{CATEGORIES[t.category] || t.category}</span><span className="chip">{STATUS[t.status] || t.status}</span>
            </li>
          ))}
        </ul>
      </section>}
      <aside className="card support-contact"><div><h2>Другие способы связи</h2><a href="mailto:hello@bukergo.ru">hello@bukergo.ru ↗</a></div><Link href="/faq">Вопросы и ответы →</Link><Link href="/legal">Документы →</Link></aside>
    </main>
  );
}
