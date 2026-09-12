"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { eventCommandKey } from "@/lib/eventCommands";
import { formatWhen, money } from "@/lib/format";

type Selection = { requirement_id: string; position: number; resource_type: "artist" | "venue"; resource_id: string; hall_id: string | null };
type Candidate = { candidate_key: string; resource_type: "artist" | "venue"; resource_id: string; hall_id: string | null; name: string; profile_href: string; reasons: string[]; warnings: string[]; presentation_facts: string[]; prices: { min_rub: number | null; max_rub: number | null }; compatibility: null | { status_label: string; hall: { name: string } } };
type Pick = Candidate & Selection & { role_label: string };
type Orientation = { state: string; min_rub: number | null; max_rub: number | null; priced_count: number; selected_count: number; note: string; methodology: string };
type Lineup = { selections: Pick[]; problems: string[]; uncovered: { label: string; position: number; required: boolean }[]; orientation: Orientation; required_total: number; required_covered: number; optional_covered: number };
type Result = { event_id: string; event_title: string; starts_at: string; ends_at: string | null; guest_count: number; declared_budget: number | null; revision: number; context_token: string; state: string; can_manage: boolean; can_adjust_end: boolean; variants_overlap: boolean; note: string; variants: (Lineup & { code: string; title: string; explanation: string })[]; current: Lineup; saved_selections: Selection[]; candidates: Record<string, Candidate[]>; requirements: { id: string; category_code: string; role_label: string; qty: number; required: boolean }[] };
const selectionKey = (s: Pick | Candidate | Selection) => `${s.resource_type}:${s.resource_id}:${s.hall_id || ""}`;
const clean = (s: Selection): Selection => ({ requirement_id: s.requirement_id, position: s.position, resource_type: s.resource_type, resource_id: s.resource_id, hall_id: s.hall_id });
const fingerprint = (items: Selection[]) => JSON.stringify(items.map(clean).sort((a, b) => a.requirement_id.localeCompare(b.requirement_id) || a.position - b.position));
function localDate(value: string | null) { return value ? new Date(new Date(value).getTime() + 3 * 3600000).toISOString().slice(0, 16) : ""; }
function OrientationView({ data }: { data: Orientation }) {
  return <div className="matching-orientation"><p className="timeline">Ориентир показанных участников</p><p className="matching-amount">{data.min_rub === null || data.max_rub === null ? "Стоимость нужно уточнить" : data.min_rub === data.max_rub ? money(data.min_rub) : `${money(data.min_rub)} — ${money(data.max_rub)}`}</p>
    <p className="timeline">Стоимость можно учесть у {data.priced_count} из {data.selected_count} выбранных участников.{data.state === "partial" ? " В сумме только известная часть." : ""}</p><p>{data.note}</p><details><summary>Как рассчитано</summary><p>{data.methodology}</p></details></div>;
}
function LineupDetails({ data }: { data: Lineup }) {
  return <><p><strong>{data.required_covered} из {data.required_total}</strong> обязательных позиций подобрано{data.optional_covered ? ` · дополнительных: ${data.optional_covered}` : ""}</p>
    <ul className="matching-picks">{data.selections.map((s) => <li key={`${s.requirement_id}-${s.position}`}><span>{s.role_label}</span><Link href={s.profile_href}>{s.name}</Link></li>)}</ul>
    {data.uncovered.some((u) => u.required) && <p className="matching-warning">Остаются обязательные позиции: {data.uncovered.filter((u) => u.required).map((u) => u.label).join(", ")}.</p>}
    <details><summary>Почему эти участники</summary>{data.selections.map((s) => <div className="matching-reasons" key={`${s.requirement_id}-${s.position}`}><h4>{s.name}</h4><ul>{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>{s.presentation_facts.length > 0 && <p>В профиле указаны: {s.presentation_facts.join(", ")}.</p>}{s.warnings.length > 0 && <><strong>Нужно уточнить</strong><ul>{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul></>}</div>)}</details>
  </>;
}

export function EventMatching({ eventId, onRequestsUpdated, contextKey }: { eventId: string; onRequestsUpdated?: () => void; contextKey?: string }) {
  const [data, setData] = useState<Result | null>(null); const [draft, setDraft] = useState<Selection[]>([]);
  const [end, setEnd] = useState(""); const [budget, setBudget] = useState("");
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const accept = useCallback((result: Result) => { setData(result); setDraft(result.saved_selections); setEnd(localDate(result.ends_at)); setBudget(result.declared_budget == null ? "" : String(result.declared_budget)); }, []);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const result = await api<Result>(`/events/${eventId}/matching`, { signal }); if (!signal?.aborted) accept(result); }
    catch(e) { if (!signal?.aborted) setError(commerceError(e)); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [eventId, accept, contextKey]);
  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);
  const dirty = Boolean(data && fingerprint(draft) !== fingerprint(data.saved_selections));
  async function save(selections: Selection[]) {
    if (!data || busy) return; setBusy(true); setError(""); setNotice("");
    try { accept(await api<Result>(`/events/${eventId}/plan`, { method: "PUT", body: JSON.stringify({ expected_revision: data.revision, expected_context: data.context_token, selections: selections.map(clean) }) })); setNotice("Предварительный состав сохранён. Даты пока не удерживаются."); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  async function saveContext(e: React.FormEvent) {
    e.preventDefault(); if (!data || busy) return; setBusy(true); setError(""); setNotice("");
    try { accept(await api<Result>(`/events/${eventId}/planning-context`, { method: "PATCH", body: JSON.stringify({ expected_context: data.context_token, budget_rub: budget === "" ? null : Number(budget), ...(data.can_adjust_end ? { ends_at: end ? `${end}:00+03:00` : null } : {}) }) })); setNotice("Параметры сохранены. Подбор обновлён."); onRequestsUpdated?.(); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  async function sendRequests() {
    if (!data || busy || dirty) return; setBusy(true); setError(""); setNotice("");
    try {
      const latest = await api<Result>(`/events/${eventId}/matching`);
      accept(latest);
      if (latest.revision !== data.revision || latest.context_token !== data.context_token || latest.current.problems.length) throw new Error("Состав или календари изменились. Проверьте актуальные варианты перед отправкой.");
      const event = await api<{ requests: { id: string; resource_type: string; resource_id: string; requirement_id: string | null; status: string }[] }>(`/events/${eventId}`);
      for (const selected of latest.current.selections) {
        const body = { resource_type: selected.resource_type === "venue" && selected.hall_id ? "hall" : selected.resource_type, resource_id: selected.hall_id || selected.resource_id, requirement_id: selected.requirement_id };
        const earlier = event.requests.filter((r) => r.resource_type === body.resource_type && r.resource_id === body.resource_id && r.requirement_id === body.requirement_id);
        if (earlier.some((r) => !["Cancelled", "Declined", "Expired"].includes(r.status))) continue;
        const seed = earlier.length ? `${eventId}:after:${earlier.map((r) => r.id).sort().join(":")}` : eventId;
        await api(`/events/${eventId}/requests`, { method: "POST", body: JSON.stringify({ ...body, idempotency_key: await eventCommandKey(seed, body) }) });
      }
      setNotice("Заявки выбранным участникам отправлены. Договорные условия появятся после их предложений."); onRequestsUpdated?.();
    } catch(e) { setError(`Не удалось завершить отправку всем участникам. ${commerceError(e)} Повтор продолжит отправку без дубликатов сохранённых заявок.`); }
    finally { setBusy(false); }
  }
  function choose(requirement_id: string, position: number, category: string, key: string) {
    const other = draft.filter((d) => d.requirement_id !== requirement_id || d.position !== position);
    const candidate = data?.candidates[category]?.find((c) => c.candidate_key === key);
    setDraft(candidate ? [...other, { requirement_id, position, resource_type: candidate.resource_type, resource_id: candidate.resource_id, hall_id: candidate.hall_id }] : other);
  }
  return <section id="matching" className="event-matching" aria-label="Подбор состава">
    <p className="kicker">После Event Studio</p><h2>Варианты состава</h2>
    {loading && <p role="status">Проверяем календари и подбираем участников…</p>}
    {error && <div className="card" role="alert"><p>{error}</p><button type="button" disabled={busy || loading} className="secondary" onClick={() => void load()}>Обновить подбор</button><p className="timeline">Обновление заменит несохранённый выбор.</p></div>}
    {notice && <p role="status">{notice}</p>}
    {data && <><p>{data.note}</p><p className="timeline">{formatWhen(data.starts_at)}{data.ends_at ? ` — ${formatWhen(data.ends_at)}` : " · окончание пока не указано"} · {data.guest_count} гостей</p>
      <details open={data.state === "needs_window"}><summary>Окно и бюджет для подбора</summary><form className="card matching-context" onSubmit={saveContext} aria-label="Параметры подбора"><fieldset disabled={busy || !data.can_manage}><label>Окончание, по Москве<input type="datetime-local" value={end} min={localDate(data.starts_at)} disabled={!data.can_adjust_end} onChange={(e) => setEnd(e.target.value)} /></label><label>Заданный бюджет, ₽<input type="number" min={0} max={1000000000} step={1} value={budget} onChange={(e) => setBudget(e.target.value)} /></label></fieldset>{!data.can_adjust_end && <p>Окно уже используется в сделке. Его изменение нужно согласовать с участниками.</p>}{data.can_manage && <button className="btn" disabled={busy}>Сохранить параметры</button>}</form></details>
      {data.state === "needs_window" ? <p className="empty">Для проверки доступности нужно будущее окно с началом и окончанием.</p> : data.state === "needs_roles" ? <p className="empty">Добавьте нужные роли в составе события ниже. Затем обновите подбор.</p> : <>
        {data.variants_overlap && <p className="timeline">При текущем составе и доступных профилях часть вариантов совпадает. Мы показываем реальные варианты без выдуманных участников.</p>}
        <div className="matching-variants">{data.variants.map((variant) => <article className="card matching-variant" key={variant.code}><h3>{variant.title}</h3><p>{variant.explanation}</p><LineupDetails data={variant} /><OrientationView data={variant.orientation} />{data.can_manage && <button type="button" className="btn" disabled={busy || !variant.selections.length} onClick={() => void save(variant.selections)}>Выбрать «{variant.title}»</button>}</article>)}</div>
        <section className="card matching-current" aria-label="Предварительный состав"><h3>Ваш предварительный состав</h3>{data.current.problems.map((p) => <p role="alert" key={p}>{p}</p>)}{data.saved_selections.length === 0 && <p className="empty">Выберите вариант или соберите состав из подходящих участников ниже.</p>}
          <form onSubmit={(e) => { e.preventDefault(); void save(draft); }}><fieldset className="matching-choices" disabled={busy || !data.can_manage}>{data.requirements.flatMap((r) => Array.from({ length: r.qty }, (_, position) => {
            const selected = draft.find((d) => d.requirement_id === r.id && d.position === position); const key = selected ? selectionKey(selected) : ""; const candidates = data.candidates[r.category_code] || [];
            return <label key={`${r.id}-${position}`}>{r.role_label}{r.qty > 1 ? ` · ${position + 1}` : ""}{!r.required ? " · необязательно" : ""}<select value={key} onChange={(e) => choose(r.id, position, r.category_code, e.target.value)}><option value="">Пока не выбран</option>{key && !candidates.some((c) => c.candidate_key === key) && <option value={key}>Ранее выбранный участник требует проверки</option>}{candidates.map((c) => <option key={c.candidate_key} value={c.candidate_key}>{c.name}{c.prices.min_rub != null ? ` · от ${money(c.prices.min_rub)}` : " · стоимость не указана"}</option>)}</select></label>;
          }))}</fieldset>{data.can_manage && <button className="btn secondary" disabled={busy}>Сохранить изменения состава</button>}</form>
          {dirty && <p>Сначала сохраните изменения состава.</p>}
          {data.current.selections.length > 0 && <><LineupDetails data={data.current} /><OrientationView data={data.current.orientation} />{data.can_manage && <button type="button" className="btn" disabled={busy || dirty || data.current.problems.length > 0} onClick={() => void sendRequests()}>Отправить заявки выбранным участникам</button>}</>}
        </section>
      </>}
      <p><button className="secondary" disabled={busy || loading} onClick={() => void load()}>Перепроверить календари и тарифы</button></p>
    </>}
  </section>;
}
