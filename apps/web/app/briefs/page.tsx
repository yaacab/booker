"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, getActiveOrg, getToken, isWriteRole } from "@/lib/api";
import { commerceError, type CommerceMe, type CommerceOrg } from "@/lib/commerce";
import { categoryLabel } from "@/lib/copy";
import { formatWhen, money } from "@/lib/format";

type Reply = { id: string; message: string; target_id: string | null; target_type: string | null; profile_name: string | null };

type Brief = { id: string; organization_id: string; title: string; city: string; date_from: string; date_to: string; role_needed: string; guest_count_band: string; public_notes: string; event_type_label: string; budget_range: { min_rub: number; max_rub: number } | null; status: string };

export default function BriefsPage() {
  const [items, setItems] = useState<Brief[]>([]);
  const [org, setOrg] = useState<CommerceOrg | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [roleNeeded, setRoleNeeded] = useState("dj");
  const [eventType, setEventType] = useState("corporate");
  const [city, setCity] = useState("Москва");
  const [band, setBand] = useState("51-100");
  const [notes, setNotes] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [shareBudget, setShareBudget] = useState(false);
  const [budgetMin, setBudgetMin] = useState("");
  const [budgetMax, setBudgetMax] = useState("");
  const [equipment, setEquipment] = useState("");
  const [busy, setBusy] = useState(false);
  const [replies, setReplies] = useState<Record<string, Reply[]>>({});

  async function load() {
    setLoading(true); setError("");
    try {
      const data = await api<{ items: Brief[] }>("/briefs"); setItems(data.items);
      if (getToken()) {
        const me = await api<CommerceMe>("/me");
        setOrg(me.organizations.find((o) => o.id === (getActiveOrg() || me.active_organization_id)) || me.organizations[0] || null);
      }
    } catch (e) { setError(commerceError(e)); } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function publish(e: FormEvent) {
    e.preventDefault(); if (!org || busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api("/briefs", { method: "POST", body: JSON.stringify({ organization_id: org.id, title, city, role_needed: roleNeeded, event_type: eventType, guest_count_band: band, public_notes: notes,
        date_from: `${dateFrom}:00+03:00`, date_to: `${dateTo}:00+03:00`, share_budget: shareBudget,
        budget_min_rub: shareBudget ? Number(budgetMin) : undefined, budget_max_rub: shareBudget ? Number(budgetMax) : undefined,
        public_requirements: { equipment: equipment.split(",").map((s) => s.trim()).filter(Boolean) },
      }) });
      setTitle(""); setNotes(""); setMessage("Бриф опубликован. Исполнители могут отправлять отклики."); await load();
    } catch (e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  async function readReplies(id: string) {
    setError("");
    try { const result = await api<{ items: Reply[] }>(`/briefs/${id}/responses`); setReplies((previous) => ({ ...previous, [id]: result.items })); }
    catch(e) { setError(commerceError(e)); }
  }
  async function close(id: string) {
    setBusy(true); setError("");
    try { await api(`/briefs/${id}/close`, { method: "POST" }); await load(); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  return <main className="commerce-page"><p className="kicker">От идеи к команде</p><h1>Открытые брифы</h1>
    <p>Расскажите о событии и нужной роли. Публичный бриф содержит только указанные здесь сведения; бюджет публикуется с вашего разрешения.</p>
    {org && org.kind !== "customer" && <Link className="btn" href={`/cabinet/${org.kind === "artist" ? "performer" : "venue"}/opportunities`}>Подходящие заказы для моего профиля</Link>}
    {loading && <p role="status">Загружаем брифы…</p>}
    {error && <div role="alert" className="card"><p>{error}</p><button onClick={() => void load()} className="btn secondary">Повторить</button></div>}
    {message && <p role="status">{message}</p>}
    {org?.kind === "customer" && isWriteRole(org.role) && <form aria-label="Публикация брифа" onSubmit={publish} className="card opportunity-filters"><h2>Опубликовать бриф</h2><p>{org.name}</p>
      <label>Заголовок<input required maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label>Город<input required maxLength={128} value={city} onChange={(e) => setCity(e.target.value)} /></label>
      <label>Формат события<select value={eventType} onChange={(e) => setEventType(e.target.value)}>{Object.entries({ corporate: "Корпоратив", wedding: "Свадьба", birthday: "День рождения", private: "Частное событие", festival: "Фестиваль", conference: "Конференция", other: "Другое" }).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Нужная роль<select value={roleNeeded} onChange={(e) => setRoleNeeded(e.target.value)}>{["dj","host","cover","photo","venue","catering","decor","makeup"].map((role) => <option key={role} value={role}>{categoryLabel(role)}</option>)}</select></label>
      <fieldset><legend>Диапазон дат и времени — по Москве</legend><label>Начало<input type="datetime-local" required value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label><label>Окончание<input type="datetime-local" required value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label></fieldset>
      <label>Число гостей<select value={band} onChange={(e) => setBand(e.target.value)}>{["1-50","51-100","101-200","200+"].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="commerce-actions"><input type="checkbox" checked={shareBudget} onChange={(e) => setShareBudget(e.target.checked)} />Разрешаю опубликовать диапазон бюджета этого брифа</label>
      {shareBudget && <fieldset><legend>Публичный бюджет</legend><label>От, ₽<input type="number" required min={0} max={1000000000} value={budgetMin} onChange={(e) => setBudgetMin(e.target.value)} /></label><label>До, ₽<input type="number" required min={0} max={1000000000} value={budgetMax} onChange={(e) => setBudgetMax(e.target.value)} /></label></fieldset>}
      <label>Необходимое оборудование, через запятую<input value={equipment} onChange={(e) => setEquipment(e.target.value)} maxLength={1000} /></label>
      <label>Публичное описание<textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} rows={3} /></label>
      <button className="btn" disabled={busy}>{busy ? "Публикуем…" : "Опубликовать бриф"}</button>
    </form>}
    {!org && !loading && <p><Link href="/login?next=%2Fbriefs">Войти, чтобы опубликовать бриф</Link></p>}
    <div className="opportunity-list">{items.map((brief) => <article className="card" key={brief.id} aria-label={brief.title}><p className="kicker">{brief.event_type_label} · {categoryLabel(brief.role_needed)}</p><h2>{brief.title}</h2><p>{brief.city} · {brief.guest_count_band} гостей</p><p>{formatWhen(brief.date_from)} — {formatWhen(brief.date_to)}</p><p>{brief.budget_range ? `Бюджет: ${money(brief.budget_range.min_rub)} — ${money(brief.budget_range.max_rub)}` : "Бюджет не опубликован"}</p>{brief.public_notes && <p>{brief.public_notes}</p>}{org?.id === brief.organization_id && <div className="commerce-actions"><button className="btn secondary" onClick={() => void readReplies(brief.id)}>Посмотреть отклики</button>{isWriteRole(org.role) && <button className="btn secondary" disabled={busy} onClick={() => void close(brief.id)}>Закрыть бриф</button>}</div>}{replies[brief.id] && <section aria-label="Отклики на бриф">{replies[brief.id].length ? replies[brief.id].map((reply) => <div className="card" key={reply.id}><h3>{reply.profile_name || "Отклик исполнителя"}</h3><p>{reply.message}</p>{reply.target_id && <Link className="btn secondary" href={`/${reply.target_type === "artist" ? "artists" : "venues"}/${reply.target_id}?date=${brief.date_from.slice(0,10)}`}>Открыть профиль и обсудить заявку</Link>}</div>) : <p>Откликов пока нет.</p>}</section>}</article>)}</div>
    {!items.length && !loading && !error && <p className="empty">Открытых брифов пока нет.</p>}
  </main>;
}
