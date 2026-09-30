"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { money } from "@/lib/format";

type Estimate = { state: "empty" | "unknown" | "partial" | "complete"; min_rub: number | null; max_rub: number | null; coverage_label: string; note: string; methodology: string };

export default function StudioEstimate({ artistIds, venueId }: { artistIds: string[]; venueId?: string }) {
  const selectionKey = JSON.stringify([...artistIds.map((id) => ({ resource_type: "artist", resource_id: id })), ...(venueId ? [{ resource_type: "venue", resource_id: venueId }] : [])]);
  const [result, setResult] = useState<{ key: string; data: Estimate } | null>(null);
  const [error, setError] = useState(""); const [revision, setRevision] = useState(0); const [loading, setLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setError(""); setResult(null);
    if (selectionKey === "[]") { setLoading(false); return; }
    setLoading(true);
    const timer = window.setTimeout(() => {
      void api<Estimate>("/event-studio/estimate", { method: "POST", signal: controller.signal, body: JSON.stringify({ selections: JSON.parse(selectionKey) }) })
        .then((data) => setResult({ key: selectionKey, data })).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [selectionKey, revision]);
  const data = result?.key === selectionKey ? result.data : null;
  return <div className="studio-estimate" role="region" aria-label="Ориентир бюджета">
    <small>Ориентир бюджета</small>
    {loading ? <span aria-live="polite">Считаем по опубликованным тарифам…</span> : error ? <><span role="alert">{error}</span><button type="button" onClick={() => setRevision((r) => r + 1)}>Повторить расчёт</button></> : data?.min_rub != null && data.max_rub != null ? <>
      <strong>{data.min_rub === data.max_rub ? money(data.min_rub) : `${money(data.min_rub)} — ${money(data.max_rub)}`}</strong>
      {data.state === "partial" && <span>Только известная часть состава.</span>}
      <span>{data.coverage_label}</span>
    </> : <strong>{selectionKey === "[]" ? "Добавьте участников" : "У выбранных участников нет опубликованной стоимости"}</strong>}
    <span>{data?.note || "Ориентировочная стоимость. Итоговые условия формируются только после предложений участников."}</span>
    {data && <details><summary>Как рассчитано</summary><p>{data.methodology}</p></details>}
  </div>;
}
