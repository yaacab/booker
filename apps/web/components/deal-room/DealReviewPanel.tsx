"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export type DealReviewsState = {
  can_submit: boolean;
  my_review?: { id: string; rating: number; text: string; created_at?: string | null } | null;
  reviews_on_booking?: number;
  pending_counterparty?: boolean;
  target_org_id?: string;
  target_org_name?: string | null;
} | null;

type Props = {
  bookingId: string;
  reviews: DealReviewsState;
  onChanged: () => void;
};

export function DealReviewPanel({ bookingId, reviews, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!reviews) return null;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api(`/bookings/${encodeURIComponent(bookingId)}/reviews`, {
        method: "POST",
        body: JSON.stringify({
          rating: Number(data.get("rating") || 5),
          text: String(data.get("text") || "").trim(),
        }),
      });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить отзыв");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" data-testid="deal-review-panel">
      <h2>Отзыв о сделке</h2>
      {reviews.my_review ? (
        <p>
          Вы оценили{reviews.target_org_name ? ` «${reviews.target_org_name}»` : ""} на{" "}
          <strong>{reviews.my_review.rating}/5</strong>
          {reviews.my_review.text ? ` — ${reviews.my_review.text}` : ""}.
        </p>
      ) : reviews.can_submit ? (
        <form className="cabinet-inline-form" onSubmit={(e) => void onSubmit(e)}>
          <p>
            Сделка завершена. Оставьте отзыв
            {reviews.target_org_name ? ` о «${reviews.target_org_name}»` : ""}.
          </p>
          <label>
            Оценка
            <select name="rating" defaultValue="5" required>
              {[5, 4, 3, 2, 1].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Комментарий
            <textarea name="text" rows={3} placeholder="Что прошло хорошо или что улучшить" />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Отправляем…" : "Отправить отзыв"}
          </button>
        </form>
      ) : (
        <p className="timeline">Отзыв для вашей роли сейчас недоступен.</p>
      )}
      {reviews.pending_counterparty ? (
        <p className="timeline">Ждём отзыв второй стороны — публикация взаимная по факту.</p>
      ) : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
    </section>
  );
}
