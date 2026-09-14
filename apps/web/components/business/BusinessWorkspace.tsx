"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { eventCommandKey, eventCommandSeed } from "@/lib/eventCommands";
import { categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";

type Brief = { city: string; event_type: string; guest_count: number; budget_rub: number | null; requirements: { category_code: string; qty: number; required: boolean }[] };
type Template = { id: string; name: string; brief: Brief };
type Templates = { items: Template[]; can_manage: boolean; can_create: boolean };
type EventItem = { id: string; title: string; city: string };
export function BusinessWorkspace({ orgId }: { orgId: string }) {
  const router = useRouter();
  const [data, setData] = useState<Templates | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [source, setSource] = useState("");
  const [title, setTitle] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    Promise.all([api<Templates>(`/business/organizations/${orgId}/templates`, { signal: controller.signal }), api<{ items: EventItem[] }>(`/events?organization_id=${orgId}`, { signal: controller.signal })])
      .then(([templates, list]) => { if (!controller.signal.aborted) { setData(templates); setEvents(list.items); setError(""); } })
      .catch(e => { if (!controller.signal.aborted) setError(commerceError(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [orgId, revision]);
  const activeTemplate = source.startsWith("template:") ? data?.items.find(t => `template:${t.id}` === source) : null;
  const activeEvent = source.startsWith("event:") ? events.find(e => `event:${e.id}` === source) : null;
  async function saveTemplate() {
    if (!activeEvent) return; setBusy(true); setError(""); setMessage("");
    try {
      const payload = { source_event_id: activeEvent.id, name: templateName.trim() };
      const key = await eventCommandKey(eventCommandSeed(`business-template:${orgId}`), payload);
      await api(`/business/organizations/${orgId}/templates`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(payload) });
      sessionStorage.removeItem(`business-template:${orgId}`);
      setMessage("Шаблон сохранён. Изменения исходного события не меняют его параметры."); setRevision(v => v + 1);
    } catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault(); if (!activeTemplate && !activeEvent) return; setBusy(true); setError("");
    try {
      const url = activeTemplate ? `/business/templates/${activeTemplate.id}/events` : `/business/events/${activeEvent!.id}/clone`;
      const payload = { title, event_date: `${start}:00+03:00`, ends_at: `${end}:00+03:00` };
      const key = await eventCommandKey(eventCommandSeed(`business-draft:${orgId}`), { url, ...payload });
      const result = await api<{ id: string }>(url, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(payload) });
      router.push(`/events/${result.id}`);
    } catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  async function archive(id: string) {
    setBusy(true); setError("");
    try { await api(`/business/templates/${id}/archive`, { method: "POST" }); if (source === `template:${id}`) setSource(""); setRevision(v => v + 1); setMessage("Шаблон убран в архив. Созданные события сохранены."); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  return <section className="card commerce-checkout" aria-label="Шаблоны и копирование событий">
    <h2>Шаблоны и копирование событий</h2>
    <p>Повторяйте формат, город, число гостей, бюджет и роли. Новые даты и состав проверяются заново; сделки, брони, подписи и внутренние заметки остаются в исходном событии.</p>
    {loading && <p role="status">Загружаем шаблоны и события…</p>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {data && <>
      {!data.can_create && <p>Для создания шаблонов и копий нужен <Link href="/pricing">тариф Business</Link>. Сохранённые шаблоны остаются доступны для просмотра.</p>}
      {!data.items.length && <p>Шаблонов пока нет. Выберите своё событие и сохраните его параметры.</p>}
      <div className="commerce-checkout">{data.items.map(item => <article key={item.id}>
        <h3>{item.name}</h3><p>{item.brief.event_type || "Формат не указан"} · {item.brief.city} · {item.brief.guest_count} гостей</p>
        <p>Плановый бюджет: {item.brief.budget_rub === null ? "не указан" : money(item.brief.budget_rub)}</p>
        <ul>{item.brief.requirements.map((role, i) => <li key={i}>{categoryLabel(role.category_code)} × {role.qty}{!role.required && " · необязательно"}</li>)}</ul>
        <div className="commerce-actions"><button className="btn secondary" type="button" disabled={busy || loading} onClick={() => { setSource(`template:${item.id}`); setTitle(item.name); }}>Выбрать шаблон: {item.name}</button>
          {data.can_manage && <button className="btn secondary" type="button" disabled={busy || loading} onClick={() => void archive(item.id)}>В архив: {item.name}</button>}</div>
      </article>)}</div>
      {data.can_manage && data.can_create ? <>
        <label className="commerce-org">Основа нового события<select value={source} disabled={busy || loading} onChange={e => setSource(e.target.value)}><option value="">Выберите событие или шаблон</option><optgroup label="События">{events.map(event => <option key={event.id} value={`event:${event.id}`}>{event.title} · {event.city}</option>)}</optgroup><optgroup label="Шаблоны">{data.items.map(item => <option key={item.id} value={`template:${item.id}`}>{item.name}</option>)}</optgroup></select></label>
        {activeEvent && <div><p><Link href={`/events/${activeEvent.id}`}>Посмотреть исходное событие</Link></p><label className="commerce-org">Название шаблона<input value={templateName} maxLength={128} onChange={e => setTemplateName(e.target.value)} /></label><button className="btn secondary" type="button" disabled={busy || loading || !templateName.trim()} onClick={() => void saveTemplate()}>Сохранить как шаблон</button></div>}
        <form onSubmit={e => void create(e)} className="commerce-checkout"><label className="commerce-org">Название нового события<input required value={title} maxLength={255} onChange={e => setTitle(e.target.value)} /></label><label className="commerce-org">Новое начало, по Москве<input required type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></label><label className="commerce-org">Новое окончание, по Москве<input required type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} /></label><button className="btn" disabled={busy || loading || (!activeEvent && !activeTemplate)}>{busy ? "Сохраняем…" : "Создать черновик"}</button></form>
      </> : !data.can_manage && <p>Создать событие или шаблон может менеджер организации.</p>}
    </>}
    <p><button className="btn secondary" type="button" disabled={busy || loading} onClick={() => setRevision(v => v + 1)}>Обновить шаблоны</button></p>
  </section>;
}
