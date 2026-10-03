"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { InvestorVenueCatalog, type InvestorVenue } from "@/components/InvestorVenueCatalog";

type CatalogResponse = { items: InvestorVenue[] };

export default function InvestorVenuesPrivate() {
  const [items, setItems] = useState<InvestorVenue[]>([]);
  const [state, setState] = useState<"loading" | "denied" | "ready">("loading");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setState("denied");
      return;
    }
    let active = true;
    const revokeOnSessionChange = () => {
      if (getToken() === token) return;
      active = false;
      setItems([]);
      setState("denied");
    };
    window.addEventListener("storage", revokeOnSessionChange);
    document.addEventListener("visibilitychange", revokeOnSessionChange);
    api<CatalogResponse>("/catalog/demo/venues?city=" + encodeURIComponent("Москва") + "&limit=300")
      .then((result) => {
        if (!active || getToken() !== token) return;
        setItems(Array.isArray(result.items) ? result.items : []);
        setState("ready");
      })
      .catch(() => {
        if (active) setState("denied");
      });
    return () => {
      active = false;
      window.removeEventListener("storage", revokeOnSessionChange);
      document.removeEventListener("visibilitychange", revokeOnSessionChange);
    };
  }, []);

  if (state !== "ready") {
    return (
      <main className="page-enter investor-venues-page">
        <h1>Исследовательские площадки</h1>
        {state === "loading" ? <p>Проверяем доступ…</p> : null}
        {state === "denied" ? (
          <p>Витрина доступна только администратору. <Link href="/login">Войти</Link></p>
        ) : null}
      </main>
    );
  }

  return (
    <main className="page-enter investor-venues-page">
      <header className="workspace-heading investor-venues-heading">
        <div>
          <p className="kicker">Закрытая исследовательская витрина · Москва</p>
          <h1>Площадки для выступлений</h1>
          <p>Данные из открытых источников требуют проверки представителем перед публикацией.</p>
        </div>
        <Link className="btn secondary" href="/search?city=Москва&kind=venue">Публичный каталог</Link>
      </header>
      <aside className="investor-venue-notice">
        Исследовательские карточки не являются опубликованными профилями партнёров. Внешние фото
        доступны только для внутренней проверки прав и источников.
      </aside>
      {items.length ? <InvestorVenueCatalog items={items} /> : (
        <article className="card empty"><h2>Карточки ещё не импортированы</h2></article>
      )}
    </main>
  );
}
