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

  async function load() {
    try {
      const data = await api<{ items: Brief[] }>("/briefs");
      setItems(data.items || []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить брифы");
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
    setBusy(true);
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
          date_from: new Date().toISOString(),
          date_to: new Date(Date.now() + 86400000).toISOString(),
        }),
      });
      setTitle("");
      setNotes("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка публикации");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Открытые брифы</h1>
      <p className="mt-2 text-sm opacity-80">
        Добровольная публикация ограниченного запроса. Телефон, email и бюджет приватного
        события сюда не попадают.
      </p>

      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <form onSubmit={onPublish} className="mt-8 grid gap-3 border-t border-black/10 pt-6">
        <h2 className="text-lg font-medium">Опубликовать бриф</h2>
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Заголовок"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Город"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Роль (dj, host, venue…)"
          value={roleNeeded}
          onChange={(e) => setRoleNeeded(e.target.value)}
          required
        />
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
        <textarea
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Публичные заметки"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
        <button
          type="submit"
          disabled={busy}
          className="justify-self-start rounded bg-[#2D6A66] px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Публикация…" : "Опубликовать"}
        </button>
      </form>

      <ul className="mt-10 space-y-4">
        {items.map((b) => (
          <li key={b.id} className="border-t border-black/10 pt-4">
            <div className="font-medium">{b.title}</div>
            <div className="mt-1 text-sm opacity-80">
              {b.city} · {b.role_needed} · {b.guest_count_band} · {b.status}
            </div>
            {b.public_notes ? <p className="mt-2 text-sm">{b.public_notes}</p> : null}
          </li>
        ))}
        {!items.length ? <li className="text-sm opacity-70">Пока нет открытых брифов.</li> : null}
      </ul>
    </main>
  );
}
