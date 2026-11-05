"use client";

import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";
import { pluralRu } from "@/lib/format";

type Reputation = {
  review_count: number;
  show_rating: boolean;
  average_rating?: number;
  note?: string;
};

type ReviewItem = {
  id: string;
  rating: number;
  text: string;
  created_at?: string | null;
};

type Props = {
  kind: "artist" | "venue";
  id: string;
};

export function OrgReviewsBlock({ kind, id }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [reputation, setReputation] = useState<Reputation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const path = kind === "artist" ? `/artists/${id}/reviews` : `/venues/${id}/reviews`;
    fetch(`${apiBase()}${path}`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Не удалось загрузить отзывы"))))
      .then((data: { items?: ReviewItem[]; reputation?: Reputation }) => {
        if (cancelled) return;
        setItems(Array.isArray(data.items) ? data.items : []);
        setReputation(data.reputation || null);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, id]);

  const count = reputation?.review_count ?? items.length;

  return (
    <section className="profile-reviews" data-testid="org-reviews-block">
      <h2>Отзывы</h2>
      {error ? <p className="timeline">{error}</p> : null}
      <p>
        {count} {pluralRu(count, "отзыв", "отзыва", "отзывов")}
        {reputation?.show_rating && reputation.average_rating != null
          ? ` · средняя ${reputation.average_rating}`
          : ""}
      </p>
      {reputation?.note ? <p className="timeline">{reputation.note}</p> : null}
      {items.length ? (
        <ul className="timeline">
          {items.slice(0, 5).map((item) => (
            <li key={item.id}>
              <strong>{item.rating}/5</strong>
              {item.text ? ` — ${item.text}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="timeline">Пока нет опубликованных отзывов.</p>
      )}
    </section>
  );
}
