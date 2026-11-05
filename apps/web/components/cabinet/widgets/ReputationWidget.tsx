"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { pluralRu } from "@/lib/format";
import { DashboardWidget } from "../DashboardWidget";

type Reputation = {
  review_count: number;
  show_rating: boolean;
  average_rating?: number;
  note?: string;
};

type Props = {
  orgId: string;
  accent?: "venue" | "performer" | "customer" | "neutral";
};

export function ReputationWidget({ orgId, accent = "neutral" }: Props) {
  const [data, setData] = useState<Reputation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api<Reputation>(`/organizations/${encodeURIComponent(orgId)}/reputation`)
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "Не удалось загрузить репутацию");
      });
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  const count = data?.review_count ?? 0;

  return (
    <DashboardWidget
      title="Репутация"
      hint="Факты по отзывам. Звёзды — после десяти."
      accent={accent}
      isEmpty={!data && !error}
      empty="Загружаем…"
    >
      {error ? <p className="timeline">{error}</p> : null}
      {data ? (
        <>
          <p data-testid="reputation-count">
            {count} {pluralRu(count, "отзыв", "отзыва", "отзывов")}
            {data.show_rating && data.average_rating != null ? ` · средняя ${data.average_rating}` : ""}
          </p>
          {data.note ? <p className="timeline">{data.note}</p> : null}
        </>
      ) : null}
    </DashboardWidget>
  );
}
