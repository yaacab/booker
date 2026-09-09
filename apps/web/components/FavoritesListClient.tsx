"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";
import { FavoriteToggle } from "@/components/FavoriteToggle";

type FavoriteItem = {
  id: string;
  target_type: "artist" | "venue";
  target_id: string;
  name?: string | null;
  city?: string | null;
  created_at?: string | null;
};

export function FavoritesListClient() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState<FavoriteItem[]>([]);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      setError("Войдите, чтобы видеть избранное.");
      return;
    }
    let cancelled = false;
    api<{ items: FavoriteItem[] }>("/favorites")
      .then((res) => {
        if (!cancelled) {
          setItems(res.items || []);
          setError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "Не удалось загрузить избранное");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <main className="favorites-v3">
        <p className="kicker">Букер</p>
        <h1>Избранное</h1>
        <div className="grid">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </main>
    );
  }

  if (!getToken()) {
    return (
      <main className="favorites-v3">
        <p className="kicker">Букер</p>
        <h1>Избранное</h1>
        <p>{error}</p>
        <p>
          <Link className="btn" href={loginHref("/cabinet/customer/favorites")}>
            Войти
          </Link>
        </p>
      </main>
    );
  }

  const artistItems = items.filter((i) => i.target_type === "artist");
  const venueItems = items.filter((i) => i.target_type === "venue");

  return (
    <main className="favorites-v3">
      <section className="favorites-v3-head">
        <div>
          <p className="kicker">Кабинет заказчика</p>
          <h1>Избранное</h1>
          <p className="timeline">Сохранённые артисты и площадки. Сохранение не создаёт заявку и не бронирует слот.</p>
        </div>
        <div className="favorites-v3-actions">
          <Link className="btn secondary" href="/cabinet/customer">К кабинету</Link>
          <Link className="btn" href="/search">Каталог</Link>
        </div>
      </section>

      <div className="favorites-v3-stats">
        <article><strong>{artistItems.length}</strong><span>артистов</span></article>
        <article><strong>{venueItems.length}</strong><span>площадок</span></article>
        <article><strong>{items.length}</strong><span>всего</span></article>
      </div>

      <div className="favorites-v3-actions">
        {artistItems.length >= 2 ? (
          <Link className="btn secondary" href={`/compare?type=artist&ids=${artistItems.slice(0, 4).map((i) => i.target_id).join(",")}`}>
            Сравнить артистов
          </Link>
        ) : null}
        {venueItems.length >= 2 ? (
          <Link className="btn secondary" href={`/compare?type=venue&ids=${venueItems.slice(0, 4).map((i) => i.target_id).join(",")}`}>
            Сравнить площадки
          </Link>
        ) : null}
      </div>

      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {!error && items.length === 0 ? (
        <article className="card empty favorites-v3-empty">
          <h2>Пока пусто</h2>
          <p>Отметьте артиста или площадку кнопкой «В избранное» в каталоге или на профиле.</p>
          <Link className="btn" href="/search">Открыть каталог</Link>
        </article>
      ) : null}

      {items.length > 0 ? (
        <div className="favorites-v3-grid">
          {items.map((item) => {
            const href = item.target_type === "artist" ? `/artists/${item.target_id}` : `/venues/${item.target_id}`;
            const kind = item.target_type === "artist" ? "Артист" : "Площадка";
            return (
              <article className="card favorites-v3-card" key={item.id}>
                <div className="favorites-v3-card-type">{kind}</div>
                <h2><Link href={href}>{item.name || item.target_id}</Link></h2>
                <p className="timeline">{item.city || "Город не указан"}</p>
                <div className="favorites-v3-actions">
                  <Link className="btn" href={href}>Открыть</Link>
                  <FavoriteToggle
                    targetType={item.target_type}
                    targetId={item.target_id}
                    onChanged={(favorited) => {
                      if (!favorited) setItems((prev) => prev.filter((row) => row.id !== item.id));
                    }}
                  />
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </main>
  );
}
