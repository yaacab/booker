"use client";

import { useEffect, useRef, useState } from "react";
import { CatalogResultCard } from "@/components/CatalogResultCard";
import { apiBase } from "@/lib/api";

export type SearchItem = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  has_calendar?: boolean;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
  address?: string;
  metro?: string;
  availability_mode?: string;
  listing_origin?: string;
  source_type?: string;
  partnership_status?: string;
  public_disclosure?: string | null;
  cover_photo?: {
    url: string;
    source_url?: string;
    rights_status?: "owned" | "licensed" | "official_permission";
  } | null;
  matching_halls?: { id: string; name: string; capacity: number }[];
};

type Props = {
  initialItems: SearchItem[];
  initialVenues: SearchItem[];
  initialCursor: string | null;
  filters: string;
  detailQuery: string;
  date?: string;
};

export function CatalogSearchResults({
  initialItems, initialVenues, initialCursor, filters, detailQuery, date,
}: Props) {
  const [items, setItems] = useState(initialItems);
  const [venues, setVenues] = useState(initialVenues);
  const [cursor, setCursor] = useState(initialCursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  async function loadMore() {
    if (!cursor || loading || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams(filters);
      params.set("cursor", cursor);
      const response = await fetch(`${apiBase()}/catalog/search-page?${params.toString()}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Каталог временно недоступен.");
      const page = await response.json();
      if (!Array.isArray(page.items) || !Array.isArray(page.venues)) {
        throw new Error("Не удалось загрузить следующую страницу.");
      }
      setItems((previous) => {
        const ids = new Set(previous.map((item) => item.id));
        return [...previous, ...page.items.filter((item: SearchItem) => !ids.has(item.id))];
      });
      setVenues((previous) => {
        const ids = new Set(previous.map((item) => item.id));
        return [...previous, ...page.venues.filter((item: SearchItem) => !ids.has(item.id))];
      });
      setCursor(typeof page.next_cursor === "string" ? page.next_cursor : null);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Каталог временно недоступен.");
      }
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  const suffix = detailQuery ? `?${detailQuery}` : "";
  return (
    <>
      {items.length > 0 ? (
        <>
          {venues.length > 0 ? <h2>Артисты</h2> : null}
          <div className="grid">
            {items.map((item) => (
              <CatalogResultCard key={item.id} item={item} kind="artist"
                href={`/artists/${item.id}${suffix}`} date={date} />
            ))}
          </div>
        </>
      ) : null}
      {venues.length > 0 ? (
        <>
          {items.length > 0 ? <h2>Площадки</h2> : null}
          <div className="grid">
            {venues.map((item) => (
              <CatalogResultCard key={item.id} item={item} kind="venue"
                href={`/venues/${item.id}${suffix}`} date={date} />
            ))}
          </div>
        </>
      ) : null}
      {error ? <p role="alert">{error} Уже загруженные варианты сохранены.</p> : null}
      {cursor ? (
        <div style={{ marginTop: 24 }}>
          <button className="btn secondary" type="button" onClick={loadMore} disabled={loading}>
            {loading ? "Загружаем…" : "Показать ещё"}
          </button>
        </div>
      ) : null}
    </>
  );
}
