"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { money } from "@/lib/format";

type BudgetLine = { booking_id: string; quote_id: string | null; role_label: string; name: string; group: string; included: boolean; customer_total_rub: number | null; reason: string; href: string };
type Budget = { declared_budget: number | null; confirmed_total: number | null; active_offers_total: number | null; estimated_remaining: number | null; state: string; methodology: string; warnings: string[]; lines: BudgetLine[]; uncovered_requirements: { requirement_id: string; position: number; label: string; required: boolean }[]; orientation: { min_rub: number | null; max_rub: number | null; priced_count: number; selected_count: number; note: string; items: { requirement_id: string; position: number; label: string; name: string; min_rub: number | null; max_rub: number | null }[] } };
const LABEL: Record<string, string> = { no_budget: "Бюджет пока не задан", partial: "Расчёт пока неполный", over_budget: "Учтённые суммы превышают бюджет", within_budget: "Учтённые предложения укладываются в бюджет" };
const amount = (value: number | null) => value === null ? "Пока неизвестно" : money(value);
export function EventBudget({ eventId, refreshKey }: { eventId: string; refreshKey?: object }) {
  const [data, setData] = useState<Budget | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const next = await api<Budget>(`/events/${eventId}/budget-summary`, { signal }); if (!signal?.aborted) setData(next); }
    catch (e) { if (!signal?.aborted) setError(commerceError(e)); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [eventId]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load, refreshKey]);
  return <section id="budget" className="event-budget card" aria-label="Бюджет события">
    <p className="kicker">Контроль расходов</p><h2>Бюджет события</h2>
    {loading && <p role="status">Обновляем суммы сделок…</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      <p className="budget-state">{LABEL[data.state] || "Проверьте состав расчёта"}</p>
      <dl className="budget-amounts">
        <div><dt>Заданный бюджет</dt><dd>{amount(data.declared_budget)}</dd></div>
        <div><dt>Подтверждённые сделки</dt><dd>{amount(data.confirmed_total)}</dd></div>
        <div><dt>Учтённые предложения</dt><dd>{amount(data.active_offers_total)}</dd></div>
        <div><dt>Остаток после учтённых сумм</dt><dd>{amount(data.estimated_remaining)}</dd></div>
      </dl>
      <p>{data.methodology}</p>
      {data.warnings.map((warning) => <p className="matching-warning" key={warning}>{warning}</p>)}
      {data.uncovered_requirements.length > 0 && <div><h3>Позиции без учтённого предложения</h3><ul>{data.uncovered_requirements.map((r) => <li key={`${r.requirement_id}-${r.position}`}>{r.label}{r.position > 0 ? ` · ${r.position + 1}` : ""}{r.required ? "" : " · необязательно"}</li>)}</ul><p>Расходы на эти позиции ещё не вычтены из остатка.</p></div>}
      {data.lines.length === 0 ? <p className="empty">Предложений ещё нет. После ответа участника здесь появится его серверная цена со сбором заказчика.</p> : <details><summary>Какие сделки и предложения входят в расчёт</summary><ul className="budget-lines">{data.lines.map((line) => <li key={line.booking_id}><div><strong>{line.name}</strong><p>{line.role_label} · {line.reason}</p></div><p>{amount(line.customer_total_rub)} · {line.included ? "учтено" : "отдельно от суммы"}</p><Link href={line.href}>Открыть сделку</Link></li>)}</ul></details>}
      {data.orientation.selected_count > 0 && <div className="budget-hints"><h3>Ориентир оставшегося выбора</h3><p className="matching-amount">{data.orientation.min_rub === null ? "Стоимость нужно уточнить" : data.orientation.min_rub === data.orientation.max_rub ? amount(data.orientation.min_rub) : `${amount(data.orientation.min_rub)} — ${amount(data.orientation.max_rub)}`}</p><p>Известна стоимость {data.orientation.priced_count} из {data.orientation.selected_count} предварительно выбранных участников без учтённого предложения. Сервисный сбор здесь ещё не рассчитан. Доступность проверяется в подборе.</p><p>{data.orientation.note}</p></div>}
      <p><a href="#matching">Изменить бюджет или предварительный состав</a></p>
    </>}
    <button type="button" className="secondary" disabled={loading} onClick={() => void load()}>Обновить бюджет</button>
  </section>;
}
