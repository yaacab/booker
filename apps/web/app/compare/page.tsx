"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { ProfileMedia } from "@/components/ProfileMedia";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { categoryLabel, CATEGORY } from "@/lib/copy";
import { guestsLabel } from "@/lib/format";

type CompareColumn = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  capacity: number | string | null;
  honorarium_hint: string;
  media_url?: string | null;
};

function CompareInner() {
  const params = useSearchParams();
  const targetType = (params.get("type") || "artist").toLowerCase();
  const idsParam = params.get("ids") || "";
  const ids = idsParam.split(",").map((s) => s.trim()).filter(Boolean);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<string[]>([]);
  const [columns, setColumns] = useState<CompareColumn[]>([]);
  const [note, setNote] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (ids.length < 2 || ids.length > 4 || new Set(ids).size !== ids.length || !["artist", "venue"].includes(targetType)) {
      setReady(true);
      setColumns([]);
      setFields([]);
      setError("Выберите от 2 до 4 разных артистов или площадок в избранном.");
      return;
    }
    let cancelled = false;
    setReady(false);
    setError("");
    api<{ fields: string[]; columns: CompareColumn[]; note?: string }>(
      `/compare?target_type=${encodeURIComponent(targetType)}&ids=${encodeURIComponent(ids.join(","))}`,
    )
      .then(async (data) => {
        const enriched = await Promise.all((data.columns || []).map(async (column) => {
          try {
            const profile = await api<{ media_url?: string | null }>(`/${targetType === "artist" ? "artists" : "venues"}/${encodeURIComponent(column.id)}`);
            return { ...column, media_url: profile.media_url };
          } catch { return column; }
        }));
        if (cancelled) return;
        setFields(data.fields || []);
        setColumns(enriched);
        setNote((data.note || "").replace("серверный ориентир", "предварительный ориентир"));
        setError("");
      })
      .catch((e: Error) => {
        if (!cancelled) { setColumns([]); setError(e instanceof ApiError ? e.message : "Не удалось сравнить"); }
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [targetType, idsParam]);

  const fieldLabels: Record<string, string> = { city: "Город", category: "Категория", verified: "Проверка профиля", capacity: "Вместимость", honorarium_hint: "Стоимость" };
  const profileHref = (id: string) => `/${targetType === "venue" ? "venues" : "artists"}/${id}`;
  const displayedFields = fields.filter((field) => field !== "name" && !(field === "capacity" && targetType === "artist"));

  return (
    <main className="compare-reference catalog-reference page-enter">
      <Link className="profile-back" href="/cabinet/customer/favorites">← К избранному</Link>
      <header className="compare-heading"><div><h1>Сравнение кандидатов</h1><p>Сравните профили и выберите тех, кто лучше всего подходит вашему событию.</p></div><p className="compare-heading-note">Разные таланты.<br />Одно большое событие.</p></header>
      {!ready ? <div className="saved-collection-grid" aria-label="Загрузка сравнения"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div> : null}
      {ready && error ? <article className="card saved-empty-state"><span className="saved-empty-icon" aria-hidden="true">⇄</span><h2>Кого сравним?</h2><p role="alert">{error}</p><div className="saved-empty-actions"><Link className="btn" href="/cabinet/customer/favorites">Выбрать из избранного</Link><Link className="btn secondary" href="/search">Открыть каталог</Link></div></article> : null}
      {ready && !error && columns.length > 0 ? <div className="compare-layout">
        <aside className="compare-categories"><p>Подобрать ещё</p><nav aria-label="Найти кандидатов по категории">{Object.entries(CATEGORY).map(([code, label]) => <Link key={code} href={`/search?${new URLSearchParams({ category: code, kind: code === "venue" ? "venue" : "artist" }).toString()}`} className={columns.some((column) => column.category === code) ? "is-active" : undefined}><span aria-hidden="true">{code === "venue" ? "⌂" : code === "dj" ? "♫" : code === "photo" ? "◎" : "◇"}</span>{label}</Link>)}</nav></aside>
        <div className="compare-results"><div className="compare-table-scroll" tabIndex={0} role="region" aria-label="Таблица сравнения кандидатов"><table className="compare-table" style={{ minWidth: `${135 + columns.length * 210}px` }}><caption className="catalog-sr-only">Публичные сведения о выбранных кандидатах</caption><thead><tr><th scope="col" className="compare-row-label">{columns.length} кандидата</th>{columns.map((column) => <th scope="col" key={column.id}><div className="compare-profile-heading"><div className="compare-profile-media"><Link href={profileHref(column.id)} aria-label={`Открыть профиль: ${column.name}`}><ProfileMedia src={column.media_url} name={column.name} compact /></Link><FavoriteToggle compact className="catalog-card-favorite" targetType={targetType === "venue" ? "venue" : "artist"} targetId={column.id} /></div><Link className="compare-profile-name" href={profileHref(column.id)}>{column.name}</Link><span className="compare-profile-category">{categoryLabel(column.category)}</span></div></th>)}</tr></thead><tbody>{displayedFields.map((field) => <tr key={field}><th scope="row">{fieldLabels[field] || "Дополнительно"}</th>{columns.map((column) => {
          const raw = (column as Record<string, unknown>)[field];
          const unknown = raw === null || raw === undefined || raw === "" || raw === "неизвестно";
          const value = unknown ? "Нет данных" : field === "category" ? categoryLabel(String(raw)) : field === "verified" ? raw ? "Подтверждён" : "Не подтверждён" : field === "capacity" && typeof raw === "number" ? `До ${guestsLabel(raw)}` : typeof raw === "boolean" ? raw ? "Да" : "Нет" : String(raw);
          return <td key={`${column.id}-${field}`} className={`${unknown ? "is-unknown" : ""}${field === "honorarium_hint" ? " compare-price-cell" : ""}`}>{field === "verified" && raw === true ? <span className="compare-verified"><span aria-hidden="true">✓</span>{value}</span> : value}</td>;
        })}</tr>)}</tbody><tfoot><tr><th scope="row"><span className="catalog-sr-only">Выбрать кандидата</span></th>{columns.map((column) => <td key={column.id}><Link className="btn" href={profileHref(column.id)}>Открыть профиль <span aria-hidden="true">↗</span></Link></td>)}</tr></tfoot></table></div>{note ? <p className="compare-note">{note}</p> : null}</div>
      </div> : null}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<main className="compare-reference"><h1>Сравнение кандидатов</h1><p>Загрузка…</p></main>}>
      <CompareInner />
    </Suspense>
  );
}
