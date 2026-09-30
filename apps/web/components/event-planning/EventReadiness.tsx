"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { formatWhen } from "@/lib/format";

type Action = { code: string; label: string; description: string; href: string };
type Overview = { event_id: string; title: string; event_date: string; city: string; state: string; score: number | null; required_total: number; required_confirmed: number; next_best_action: Action; test_payments: number };
type Readiness = Overview & { event_ready: boolean; methodology: string; checklist: { code: string; label: string; done: number; total: number; status: string; note: string }[]; blockers: Action[]; compatibility: { artist_id: string; artist_name: string; hall_name: string | null; status: string; to_resolve: { label: string; explanation: string }[] }[] };
const STATE: Record<string, string> = { planning: "Подготовка продолжается", ready: "Проверки подготовки выполнены", completed: "Событие завершено", cancelled: "Событие отменено", in_progress: "Событие проводится" };
const CHECK: Record<string, string> = { done: "Готово", pending: "Осталось выполнить", unknown: "Нужно уточнить", not_applicable: "Не требуется в этом составе" };
function Progress({ data }: { data: Pick<Overview, "score" | "required_confirmed" | "required_total" | "state" | "test_payments"> }) {
  return <><p><strong>{STATE[data.state] || "Проверьте сведения события"}</strong>{data.score !== null ? ` · ${data.score}% проверок` : ""}</p>
    {data.score !== null && <progress aria-label="Выполненные проверки подготовки" value={data.score} max={100} />}
    <p>{data.required_confirmed} из {data.required_total} обязательных позиций подтверждено сделками.</p>
    {data.test_payments > 0 && <p className="matching-warning">Тестовые подтверждения оплаты: {data.test_payments}. Деньги не списывались.</p>}</>;
}
export function EventReadiness({ eventId, refreshKey }: { eventId: string; refreshKey?: object }) {
  const [data, setData] = useState<Readiness | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const result = await api<Readiness>(`/events/${eventId}/readiness`, { signal }); if (!signal?.aborted) setData(result); }
    catch (e) { if (!signal?.aborted) setError(commerceError(e)); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [eventId]);
  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load, refreshKey]);
  return <section id="readiness" className="event-readiness card" aria-label="Готовность события"><p className="kicker">Следующий шаг</p><h2>Готовность события</h2>
    {loading && <p role="status">Проверяем состав, резервы и документы…</p>}{error && <p role="alert">{error}</p>}
    {data && <><Progress data={data} /><p>{data.methodology}</p><div className="readiness-next"><h3>{data.next_best_action.label}</h3><p>{data.next_best_action.description}</p><Link className="btn" href={data.next_best_action.href}>Продолжить организацию</Link></div>
      {!["completed", "cancelled"].includes(data.state) && <><details><summary>Все проверки подготовки</summary><ul className="readiness-checklist">{data.checklist.map((check) => <li key={check.code}><strong>{check.label}</strong><p>{CHECK[check.status]}{check.total ? ` · ${check.done} из ${check.total}` : ""}</p>{check.note && <p className="timeline">{check.note}</p>}</li>)}</ul></details>
        {data.blockers.length > 0 && <details><summary>Что осталось сделать · {data.blockers.length}</summary><ul className="readiness-checklist">{data.blockers.map((item, index) => <li key={`${item.code}-${index}`}><Link href={item.href}>{item.label}</Link><p>{item.description}</p></li>)}</ul></details>}
        {data.compatibility.some((p) => p.to_resolve.length > 0) && <details><summary>Что нужно согласовать по технике</summary>{data.compatibility.map((pair) => <div key={pair.artist_id}><h3>{pair.artist_name}{pair.hall_name ? ` · ${pair.hall_name}` : ""}</h3><ul>{pair.to_resolve.map((item) => <li key={item.label}>{item.label}: {item.explanation}</li>)}</ul></div>)}</details>}</>}
    </>}
    <p><button type="button" className="secondary" disabled={loading} onClick={() => void load()}>Обновить готовность</button></p>
  </section>;
}
export function EventReadinessOverview({ organizationId }: { organizationId: string }) {
  const [data, setData] = useState<{ items: Overview[]; note: string } | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId) return; setLoading(true); setError("");
    try { const result = await api<{ items: Overview[]; note: string }>(`/orgs/${organizationId}/event-readiness`, { signal }); if (!signal?.aborted) setData(result); }
    catch (e) { if (!signal?.aborted) setError(commerceError(e)); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [organizationId]);
  useEffect(() => { setData(null); const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);
  return <section className="readiness-overview" aria-label="Продолжить организацию событий"><h2>Продолжить организацию</h2>
    {loading && <p role="status">Проверяем ближайшие события…</p>}{error && <p role="alert">{error}</p>}
    {data && <><p className="timeline">{data.note}</p>{data.items.length === 0 ? <p>Ближайших незавершённых событий пока нет.</p> : <div className="readiness-event-grid">{data.items.map((event) => <article className="card" key={event.event_id}><h3><Link href={`/events/${event.event_id}`}>{event.title}</Link></h3><p className="timeline">{formatWhen(event.event_date)} · {event.city}</p><Progress data={event} /><p>{event.next_best_action.description}</p><Link className="btn" href={event.next_best_action.href}>Продолжить организацию</Link><p className="timeline">{event.next_best_action.label}</p></article>)}</div>}</>}
    {error && <button className="secondary" disabled={loading} onClick={() => void load()}>Обновить события</button>}
  </section>;
}
