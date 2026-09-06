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
      <main>
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
      <main>
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

  return (
    <main>
      <p className="kicker">Кабинет заказчика</p>
      <h1>Избранное</h1>
      <p className="timeline">
        Сохранённые артисты и площадки. Добавление в избранное не создаёт заявку и не бронирует слот.
      </p>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <Link className="btn secondary" href="/cabinet/customer">
          К кабинету
        </Link>
        <Link className="btn" href="/search">
          Каталог
        </Link>
      </p>
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {!error && items.length === 0 ? (
        <article className="card empty" style={{ marginTop: 20 }}>
          <h2>Пока пусто</h2>
          <p>Отметьте артиста или площадку кнопкой «В избранное» в каталоге или на профиле.</p>
          <Link className="btn" href="/search">
            Открыть каталог
          </Link>
        </article>
      ) : null}
      {items.length > 0 ? (
        <div className="grid" style={{ marginTop: 20 }}>
          {items.map((item) => {
            const href =
              item.target_type === "artist"
                ? `/artists/${item.target_id}`
                : `/venues/${item.target_id}`;
            const kind = item.target_type === "artist" ? "Артист" : "Площадка";
            return (
              <article className="card" key={item.id}>
                <div className="card-head">
                  <strong>
                    <Link href={href}>{item.name || item.target_id}</Link>
                  </strong>
                </div>
                <p className="timeline">
                  {kind}
                  {item.city ? ` · ${item.city}` : ""}
                </p>
                <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                  <Link className="btn" href={href}>
                    Открыть
                  </Link>
                  <FavoriteToggle
                    targetType={item.target_type}
                    targetId={item.target_id}
                    onChanged={(favorited) => {
                      if (!favorited) {
                        setItems((prev) => prev.filter((row) => row.id !== item.id));
                      }
                    }}
                  />
                </p>
              </article>
            );
          })}
        </div>
      ) : null}
    </main>
  );
}
