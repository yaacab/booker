"use client";

import { useState } from "react";

type RequestDraft = { slot_id: string | null; honorarium_rub: number | null };

export function RequestOfferForm<T extends RequestDraft>({ item, busy, onSend }: { item: T; busy: boolean; onSend: (item: T) => void }) {
  const [price, setPrice] = useState(item.honorarium_rub?.toString() ?? "");
  if (!item.slot_id) return <p className="timeline">Нет подтверждённого свободного интервала на всё время события. Уточните время заявки и календарь.</p>;
  return <form onSubmit={(event) => { event.preventDefault(); onSend({ ...item, honorarium_rub: Number(price) }); }}>
    <label>Гонорар предложения, ₽<input type="number" inputMode="numeric" min="1" max="1000000000" step="1" required value={price} onChange={event => setPrice(event.target.value)} disabled={busy} /></label>
    <p className="timeline">Проверьте сумму перед отправкой. Комиссию и итоговые условия рассчитает сервер. Срок предложения — до 72 часов, не позднее начала события.</p>
    <button type="submit" disabled={busy}>{busy ? "Отправляем…" : "Отправить предложение"}</button>
  </form>;
}
