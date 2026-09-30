"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";

const LABELS: Record<string, string> = { price: "Цена не подошла", customer_selected_another: "Выбран другой участник", event_cancelled: "Событие отменено", supplier_declined: "Я отказался от заявки", unknown: "Причина не указана" };

export function LossReason({ requestId, side, savedReason, onSaved }: { requestId: string; side: "customer" | "supplier"; savedReason: string | null; onSaved: () => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true); setError("");
    try { await api(`/requests/${requestId}/loss-reason`, { method: "POST", body: JSON.stringify({ reason }) }); await onSaved(); }
    catch (e) { setError(commerceError(e)); }
    finally { setBusy(false); }
  }
  return <section className="card" aria-label="Причина закрытия заявки"><h2>Почему заявка закрылась</h2>
    {savedReason ? <p>{LABELS[savedReason] || "Причина зафиксирована участником"}</p> : <>
      <p>Отметьте причину, если она известна. Это добровольная обратная связь для аналитики.</p>
      <label>Причина<select value={reason} onChange={(e) => setReason(e.target.value)}><option value="">Выберите причину</option>{(side === "customer" ? ["price", "customer_selected_another", "event_cancelled"] : ["supplier_declined"]).map((key) => <option key={key} value={key}>{LABELS[key]}</option>)}</select></label>
      <button className="btn secondary" type="button" disabled={!reason || busy} onClick={() => void submit()}>{busy ? "Сохраняем…" : "Сохранить причину"}</button>
    </>}{error && <p role="alert">{error}</p>}
  </section>;
}
