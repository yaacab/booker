"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ProfileMedia } from "@/components/ProfileMedia";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { pluralRu } from "@/lib/format";

type SharedItem = {
  target_id: string;
  name: string;
  city: string;
  summary: string;
  profile_path: string;
  media_url?: string | null;
};

export function SharedShortlistClient({ token }: { token: string }) {
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [items, setItems] = useState<SharedItem[]>([]);
  const [ready, setReady] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setShareUrl(`${window.location.origin}${window.location.pathname}`);
    setReady(false);
    setError("");
    api<{ title: string; items: SharedItem[] }>(`/shared/${encodeURIComponent(token)}`)
      .then(async (data) => {
        const enriched = await Promise.all((data.items || []).map(async (item) => {
          if (!/^\/(artists|venues)\/[^/?#]+$/.test(item.profile_path)) return item;
          try {
            const profile = await api<{ media_url?: string | null }>(item.profile_path);
            return { ...item, media_url: profile.media_url };
          } catch { return item; }
        }));
        if (cancelled) return;
        setTitle(data.title || "Подборка");
        setItems(enriched);
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

  async function copyLink() {
    setCopyError("");
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
    } catch { setCopyError("Не удалось скопировать. Выделите ссылку и скопируйте её вручную."); }
  }

  if (!ready) {
    return <main className="shared-collection-reference"><p className="kicker">Совместная подборка</p><h1>Подбираем хорошие варианты</h1><div className="saved-collection-grid" aria-label="Загрузка подборки"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div></main>;
  }

  if (error) {
    return <main className="shared-collection-reference"><Link className="profile-back" href="/search">← В каталог</Link><article className="card saved-empty-state"><span className="saved-empty-icon" aria-hidden="true">↗</span><h1>Подборка недоступна</h1><p role="alert">{error}</p><p>Ссылка могла быть отозвана или истечь. Попросите автора поделиться подборкой ещё раз.</p><Link className="btn" href="/search">Найти артистов и площадки</Link></article></main>;
  }

  return (
    <main className="shared-collection-reference catalog-reference page-enter">
      <div className="shared-link-bar"><label>Ссылка на подборку<span><input value={shareUrl} readOnly aria-label="Ссылка на подборку" /><button type="button" onClick={() => void copyLink()} aria-label="Скопировать ссылку на подборку"><svg aria-hidden="true" viewBox="0 0 24 24"><rect x="8" y="4" width="12" height="14" rx="2" /><path d="M16 18v2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h3" /></svg></button></span></label>{copied ? <span className="shared-copy-status" role="status">Ссылка скопирована</span> : null}</div>
      {copyError ? <p className="profile-error" role="alert">{copyError}</p> : null}
      <header className="shared-collection-heading"><div><p className="profile-eyebrow">Хорошие варианты — в одном месте</p><h1>{title}</h1><p>Посмотрите профили и выберите тех, кто подойдёт вашему событию.</p></div><div className="shared-start-event"><Link className="btn" href="/events/new">Создать своё событие <span aria-hidden="true">→</span></Link><p>Найдём артистов и площадки<br />под ваши задачи.</p></div></header>
      <div className="shared-collection-count"><strong>{items.length} {pluralRu(items.length, "вариант", "варианта", "вариантов")} в подборке</strong><span>Выбор начинается здесь</span></div>
      {items.length ? <div className="shared-collection-grid">{items.map((item) => {
        const targetType = item.profile_path.startsWith("/venues/") ? "venue" : "artist";
        return <article key={item.target_id} className="shared-profile-card"><div className="shared-profile-media"><Link href={item.profile_path} aria-label={`Открыть профиль: ${item.name}`}><ProfileMedia src={item.media_url} name={item.name} compact /></Link><FavoriteToggle compact className="catalog-card-favorite" targetType={targetType} targetId={item.target_id} /></div><div className="shared-profile-content"><h2><Link href={item.profile_path}>{item.name}</Link></h2>{item.summary ? <p>{item.summary}</p> : null}<div><span>{item.city}</span><Link href={item.profile_path}>Открыть профиль <span aria-hidden="true">↗</span></Link></div></div></article>;
      })}</div> : <article className="card saved-empty-state"><span className="saved-empty-icon" aria-hidden="true">♡</span><h2>Подборка пока пустая</h2><p>Пока автор добавляет варианты, вы можете посмотреть каталог.</p><Link className="btn" href="/search">Открыть каталог</Link></article>}
    </main>
  );
}
