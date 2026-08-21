"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

type Me = {
  email: string;
  full_name: string;
  is_platform_admin?: boolean;
  organizations: { id: string; name: string; kind: string; role: string }[];
};

const KIND: Record<string, string> = {
  customer: "заказчик",
  artist: "исполнитель",
  venue: "площадка",
};
const ROLE: Record<string, string> = {
  owner: "владелец",
  member: "в команде",
  admin: "админ",
};

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      setError("Нужен вход");
      return;
    }
    api<Me>("/me")
      .then(setMe)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (!getToken() && error) {
    return (
      <main>
        <h1>Профиль</h1>
        <p>
          {error}. <Link href={loginHref("/profile")}>Войти</Link>
        </p>
      </main>
    );
  }

  if (!me) {
    return (
      <main>
        <p className="kicker">Это вы</p>
        <h1>Профиль</h1>
        {error ? (
          <p>
            {error}. <Link href={loginHref("/profile")}>Войти</Link>
          </p>
        ) : (
          <div className="skeleton" />
        )}
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Это вы</p>
      <h1>{me.full_name}</h1>
      <p className="timeline">{me.email}</p>
      {me.organizations.map((o) => (
        <article className="card" key={o.id}>
          <strong>{o.name}</strong>
          <div>
            {KIND[o.kind] || o.kind} · {ROLE[o.role] || o.role}
          </div>
        </article>
      ))}
      {me.is_platform_admin ? (
        <p>
          <Link href="/admin">Пульт. Без нейронки.</Link>
        </p>
      ) : null}
      <p style={{ display: "flex", gap: 8 }}>
        <Link className="btn" href="/cabinet">
          Сделки
        </Link>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setToken(null);
            localStorage.removeItem("booker.admin");
            window.location.href = "/";
          }}
        >
          Выйти
        </button>
      </p>
    </main>
  );
}
