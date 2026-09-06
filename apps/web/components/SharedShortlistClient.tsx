"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type SharedItem = {
  target_id: string;
  name: string;
  city: string;
  summary: string;
  profile_path: string;
};

export function SharedShortlistClient({ token }: { token: string }) {
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [items, setItems] = useState<SharedItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<{ title: string; items: SharedItem[] }>(`/shared/${encodeURIComponent(token)}`)
      .then((data) => {
        if (cancelled) return;
        setTitle(data.title || "Подборка");
        setItems(data.items || []);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Ссылка недоступна");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!ready) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Подборка</h1>
        <p>Загрузка…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Подборка недоступна</h1>
        <p>{error}</p>
        <p>Ссылка могла быть отозвана или истечь.</p>
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Совместная подборка · noindex</p>
      <h1>{title}</h1>
      <p className="timeline">Только публичные факты. Без телефонов, бюджета события и переписки.</p>
      <div className="grid" style={{ marginTop: 16 }}>
        {items.map((it) => (
          <article key={it.target_id} className="card">
            <h2>{it.name}</h2>
            <p>
              {it.city}
              {it.summary ? ` · ${it.summary}` : ""}
            </p>
            <Link className="btn secondary" href={it.profile_path}>
              Открыть профиль
            </Link>
          </article>
        ))}
      </div>
    </main>
  );
}
