"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, getActiveOrg, getToken } from "@/lib/api";

type Brief = {
  id: string;
  title: string;
  city: string;
  date_from: string;
  date_to: string;
  role_needed: string;
  guest_count_band: string;
  public_notes: string;
  status: string;
};

export default function BriefsPage() {
  const [items, setItems] = useState<Brief[]>([]);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [roleNeeded, setRoleNeeded] = useState("dj");
  const [city, setCity] = useState("Москва");
  const [band, setBand] = useState("51-100");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [published, setPublished] = useState(false);

  async function load() {
    try {
      const data = await api<{ items: Brief[] }>("/briefs");
      setItems(data.items || []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить брифы");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onPublish(e: FormEvent) {
    e.preventDefault();
    const org = getActiveOrg();
    if (!getToken() || !org) {
      setError("Нужен вход и активная организация заказчика");
      return;
    }
    const starts = new Date(dateFrom);
    const ends = new Date(dateTo);
    if (!Number.isFinite(starts.getTime()) || !Number.isFinite(ends.getTime()) || ends <= starts) {
      setError("Укажите начало и окончание события. Окончание должно быть позже начала.");
      return;
    }
    setBusy(true);
    setPublished(false);
    try {
      await api("/briefs", {
        method: "POST",
        body: JSON.stringify({
          organization_id: org,
          title,
          city,
          role_needed: roleNeeded,
          guest_count_band: band,
          public_notes: notes,
          date_from: starts.toISOString(),
          date_to: ends.toISOString(),
        }),
      });
      setTitle("");
      setNotes("");
      setPublished(true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка публикации");
    } finally {
      setBusy(false);
    }
  }

  const roleLabels: Record<string, string> = { dj: "DJ", host: "Ведущий", venue: "Площадка", photographer: "Фотограф", cover_band: "Кавер-группа" };
  const visible = items.filter((b) => `${b.title} ${b.city} ${roleLabels[b.role_needed] || b.role_needed}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));

  return (
    <main className="briefs-reference">
      <header className="account-heading"><p className="kicker">Новые события — новые встречи</p><h1>Публичные брифы</h1><p>Найдите событие для своей команды или расскажите, кого ищете вы.</p></header>

      {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
      {published && <p role="status" className="support-notice">Бриф опубликован.</p>}
      <div className="briefs-columns"><section className="briefs-results"><label className="brief-search">Найти бриф<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название, город или специалист" /></label>
      <p className="timeline" role="status">{loading ? "Загружаем брифы…" : `Найдено: ${visible.length}`}</p>
      <ul className="brief-list">
        {visible.map((b) => <li key={b.id} className="card brief-card"><div className="brief-meta"><span className="chip">{roleLabels[b.role_needed] || b.role_needed}</span><span>{b.city}</span></div><h2>{b.title}</h2><p className="brief-dates">{new Date(b.date_from).toLocaleDateString("ru-RU")} — {new Date(b.date_to).toLocaleDateString("ru-RU")} · {b.guest_count_band} гостей</p>{b.public_notes && <p>{b.public_notes}</p>}<span className="timeline">{b.status === "open" ? "Открыт для предложений" : b.status === "closed" ? "Закрыт" : b.status}</span></li>)}
      </ul>
      {!loading && !error && !visible.length && <div className="card"><h2>{query ? "Брифы не найдены" : "Первое событие — за вами"}</h2><p>{query ? "Попробуйте другой город или название." : "Опубликуйте запрос и расскажите, кого вы ищете для своего события."}</p></div>}
      </section><details className="card brief-publish" open><summary>Опубликовать бриф</summary>
      <p className="timeline">Эти данные будут видны всем. Телефон, email и бюджет вашего частного события сюда не переносятся.</p>

      <form onSubmit={onPublish} className="brief-form">
        <label>Название события
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Заголовок"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        </label><label>Город
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Город"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        </label><label>Кого ищете
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Роль (dj, host, venue…)"
          value={roleNeeded}
          onChange={(e) => setRoleNeeded(e.target.value)}
          required
        />
        </label><label>Количество гостей
        <select
          className="rounded border border-black/15 px-3 py-2"
          value={band}
          onChange={(e) => setBand(e.target.value)}
        >
          <option value="1-50">1–50 гостей</option>
          <option value="51-100">51–100 гостей</option>
          <option value="101-200">101–200 гостей</option>
          <option value="200+">200+</option>
        </select>
        </label><label>Начало события<input type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} required /></label>
        <label>Окончание события<input type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} min={dateFrom || undefined} required /></label>
        <label>О событии
        <textarea
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Публичные заметки"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="justify-self-start rounded bg-[#2D6A66] px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Публикация…" : "Опубликовать"}
        </button>
      </form>
      </details></div>
    </main>
  );
}
