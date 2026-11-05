"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { ProfileMedia } from "@/components/ProfileMedia";
import { categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";

type FavoriteItem = {
  id: string;
  target_type: "artist" | "venue";
  target_id: string;
  name?: string | null;
  city?: string | null;
  created_at?: string | null;
  media_url?: string | null;
  category?: string;
  honorarium_rub?: number;
};

export function FavoritesListClient() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [activeType, setActiveType] = useState<"artist" | "venue">("artist");
  const [compareMode, setCompareMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      setError("Войдите, чтобы видеть избранное.");
      return;
    }
    let cancelled = false;
    api<{ items: FavoriteItem[] }>("/favorites")
      .then(async (res) => {
        const favorites = res.items || [];
        const enriched = await Promise.all(favorites.map(async (item) => {
          try {
            const profile = await api<{ media_url?: string | null; category?: string; tariffs?: { honorarium_rub: number }[] }>(`/${item.target_type === "artist" ? "artists" : "venues"}/${encodeURIComponent(item.target_id)}`);
            return { ...item, media_url: profile.media_url, category: profile.category, honorarium_rub: profile.tariffs?.[0]?.honorarium_rub };
          } catch { return item; }
        }));
        if (!cancelled) {
          setItems(enriched);
          if (!favorites.some((item) => item.target_type === "artist") && favorites.some((item) => item.target_type === "venue")) setActiveType("venue");
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
      <main className="saved-collection-reference">
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
      <main className="saved-collection-reference">
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

  const visibleItems = items.filter((item) => item.target_type === activeType);
  const compareIds = compareMode ? selectedIds : visibleItems.slice(0, 4).map((item) => item.target_id);
  const compareHref = `/compare?${new URLSearchParams({ type: activeType, ids: compareIds.join(",") }).toString()}`;

  return (
    <main className="saved-collection-reference catalog-reference page-enter">
      <header className="saved-collection-heading">
        <div><h1>Избранное</h1><p>Артисты и площадки, которые вам нравятся. Сравнивайте и выбирайте для своего события.</p></div>
        <Link className="btn saved-collection-add" href="/search">Найти ещё <span aria-hidden="true">↗</span></Link>
      </header>
      <div className="saved-collection-toolbar">
        <div className="saved-type-switch" role="group" aria-label="Тип избранного">
          {([{ type: "artist", label: "Артисты" }, { type: "venue", label: "Площадки" }] as const).map((tab) => <button key={tab.type} type="button" aria-pressed={activeType === tab.type} onClick={() => { setActiveType(tab.type); setSelectedIds([]); }}>{tab.label}<span>{items.filter((item) => item.target_type === tab.type).length}</span></button>)}
        </div>
        <div className="saved-comparison-controls">
          <label><input type="checkbox" checked={compareMode} onChange={(event) => { setCompareMode(event.target.checked); setSelectedIds([]); }} />Режим сравнения</label>
          {compareIds.length >= 2 ? <Link className="btn secondary" href={compareHref}>{compareMode ? `Сравнить (${selectedIds.length})` : activeType === "artist" ? "Сравнить артистов" : "Сравнить площадки"}</Link> : <button type="button" className="btn secondary" disabled>Сравнить ({compareIds.length})</button>}
        </div>
      </div>
      {compareMode ? <p className="saved-comparison-hint" role="status">Выберите от 2 до 4 {activeType === "artist" ? "артистов" : "площадок"}. Выбрано: {selectedIds.length}.</p> : null}
      {error ? <p className="profile-error" role="alert">{error}</p> : null}
      {!error && visibleItems.length === 0 ? <article className="card saved-empty-state"><span className="saved-empty-icon" aria-hidden="true">♡</span><h2>{items.length ? `В избранном пока нет ${activeType === "artist" ? "артистов" : "площадок"}` : "Здесь будут ваши любимые"}</h2><p>Нажмите на сердце в каталоге, чтобы сохранить подходящие варианты.</p><Link className="btn" href={`/search?kind=${activeType}`}>Открыть каталог <span aria-hidden="true">→</span></Link></article> : null}
      {visibleItems.length > 0 ? <div className="saved-collection-grid">{visibleItems.map((item) => {
        const href = `/${item.target_type === "artist" ? "artists" : "venues"}/${item.target_id}`;
        const name = item.name || (item.target_type === "artist" ? "Профиль артиста" : "Профиль площадки");
        const selected = selectedIds.includes(item.target_id);
        return <article className={`saved-profile-card${selected ? " is-selected" : ""}`} key={item.id}>
          <div className="saved-profile-media"><Link href={href} aria-label={`Открыть профиль: ${name}`}><ProfileMedia src={item.media_url} name={name} compact /></Link>
            {compareMode ? <label className="saved-compare-checkbox"><input type="checkbox" aria-label={`Сравнить: ${name}`} checked={selected} disabled={!selected && selectedIds.length >= 4} onChange={(event) => setSelectedIds((previous) => event.target.checked ? [...previous, item.target_id] : previous.filter((id) => id !== item.target_id))} /></label> : null}
            <FavoriteToggle compact className="catalog-card-favorite" targetType={item.target_type} targetId={item.target_id} onChanged={(favorited) => { if (!favorited) { setItems((previous) => previous.filter((row) => row.id !== item.id)); setSelectedIds((previous) => previous.filter((id) => id !== item.target_id)); } }} />
          </div>
          <div className="saved-profile-content"><h2><Link href={href}>{name}</Link></h2><p>{item.target_type === "artist" ? categoryLabel(item.category) || "Артист" : "Площадка"}{item.city ? ` · ${item.city}` : ""}</p>{item.honorarium_rub != null ? <strong className="saved-profile-price">{money(item.honorarium_rub)}<small>Ориентир</small></strong> : <span className="saved-price-request">Стоимость по запросу</span>}<Link className="btn secondary" href={href}>Открыть профиль <span aria-hidden="true">↗</span></Link></div>
        </article>;
      })}</div> : null}
      <p className="saved-collection-footnote">Сохранённые варианты всегда под рукой. Дату и условия вы согласуете после заявки.</p>
    </main>
  );
}
