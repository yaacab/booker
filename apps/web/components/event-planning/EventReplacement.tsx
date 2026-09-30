"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { eventCommandError, eventCommandKey, eventCommandSeed } from "@/lib/eventCommands";
import { formatWhen } from "@/lib/format";

type Candidate = { candidate_key: string; resource_type: string; resource_id: string; hall_id: string | null; name: string; profile_href: string; reasons: string[]; warnings: string[] };
type Plan = { needs_replacement: boolean; can_manage: boolean; open_slots: number; state: string; candidates: Candidate[]; window: { starts_at: string; ends_at: string | null }; cancelled_requests: { id: string; resource_name: string | null }[] };

export function EventReplacement({ eventId, requirementId, label, onUpdated }: { eventId: string; requirementId: string; label: string; onUpdated: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const url = `/events/${eventId}/requirements/${requirementId}/replacement`;
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api<Plan>(url).then(data => { if (!cancelled) { setPlan(data); setError(""); } })
      .catch(err => { if (!cancelled) { setPlan(null); setError(eventCommandError(err)); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [url, revision]);
  async function send(item: Candidate) {
    setBusy(item.candidate_key); setError(""); setMessage("");
    try {
      const payload = { requirement_id: requirementId, resource_type: item.hall_id ? "hall" : item.resource_type, resource_id: item.hall_id || item.resource_id };
      const idempotency_key = await eventCommandKey(eventCommandSeed(`replacement:${eventId}:${requirementId}`), payload);
      await api(`${url}-requests`, { method: "POST", body: JSON.stringify({ ...payload, idempotency_key }) });
      setMessage(`Запрос отправлен: ${item.name}. Дождитесь нового предложения — дата пока не зарезервирована.`);
      setRevision(value => value + 1); onUpdated();
    } catch (err) { setError(eventCommandError(err)); }
    finally { setBusy(""); }
  }
  if (plan && !plan.needs_replacement) return null;
  return <article className="card tint" style={{ marginTop: "0.75rem", minWidth: 0 }} aria-label={`Замена: ${label}`}>
    <strong>Замена: {label}</strong>
    {loading ? <p role="status">Проверяем доступность…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {message ? <p role="status">{message}</p> : null}
    {plan ? <>
      <p className="timeline">Открытых позиций: {plan.open_slots}. Отменённые участники: {plan.cancelled_requests.map(item => item.resource_name || "Участник").join(", ")}.</p>
      <p className="timeline">Букер покажет доступные варианты. Замена зависит от ответа участника и согласования нового предложения.</p>
      {plan.state === "needs_window" ? <p>Укажите полное будущее окно события в <Link href="#matching">подборе состава</Link>, чтобы проверить свободные даты.</p> : <>
        <p className="timeline">Проверяемое окно: {formatWhen(plan.window.starts_at)} — {formatWhen(plan.window.ends_at || plan.window.starts_at)}.</p>
        <button className="btn" type="button" aria-expanded={expanded} disabled={loading || !!busy} onClick={() => setExpanded(value => !value)}>{expanded ? "Скрыть варианты" : "Подобрать замену"}</button>
        {expanded ? <div>
          <p className="timeline">Календарь проверен на всё окно и известное время монтажа. Перед запросом сервер проверит условия ещё раз. Порядок — по имени.</p>
          {!plan.candidates.length ? <p>Свободных вариантов с подходящими условиями пока нет. Можно проверить позднее или изменить окно события.</p> : null}
          {plan.candidates.map(item => <section key={item.candidate_key} style={{ borderTop: "1px solid var(--line)", marginTop: "1rem", paddingTop: "1rem", overflowWrap: "anywhere" }} aria-label={item.name}>
            <h4><Link href={item.profile_href}>{item.name}</Link></h4>
            <ul className="timeline">{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
            {item.warnings.length ? <details><summary>Что нужно уточнить ({item.warnings.length})</summary><ul className="timeline">{item.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details> : null}
            {plan.can_manage ? <p><button className="btn" type="button" disabled={loading || !!busy} onClick={() => void send(item)}>{busy === item.candidate_key ? "Отправляем…" : "Запросить новое предложение"}</button></p> : <p className="timeline">Запрос может отправить менеджер организации.</p>}
          </section>)}
        </div> : null}
      </>}
    </> : null}
    <p><button className="btn secondary" type="button" disabled={loading || !!busy} onClick={() => setRevision(value => value + 1)}>Обновить доступность</button></p>
  </article>;
}
