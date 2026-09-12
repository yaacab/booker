"use client";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api, getActiveOrg, getToken, isWriteRole } from "@/lib/api";
import { commerceError, type CommerceMe, type CommerceOrg } from "@/lib/commerce";
import { categoryLabel } from "@/lib/copy";
import { formatWhen, money } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { SupplyCabinetNav } from "@/components/cabinet/SupplyCabinetNav";

type Match = { score: number; profile_id: string; profile_name: string; methodology: string; reasons: { code: string; state: string; label: string }[] };
type Opportunity = { id: string; title: string; event_type: string; event_type_label: string; city: string; date_from: string; date_to: string; role_needed: string; guest_count_band: string; public_notes: string; budget_range: { min_rub: number; max_rub: number } | null; match: Match; response_id: string | null };
type Feed = { items: Opportunity[]; total: number; page: number; has_more: boolean; profiles: { id: string; name: string }[]; features: Record<string, boolean | number> };
type Query = Record<string, string | number>;
type Saved = { id: string; name: string; query: Query; instant_alerts: boolean };

export function OpportunityFeed({ audience }: { audience: "artist" | "venue" }) {
  const [org, setOrg] = useState<CommerceOrg | null>(null);
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<Feed | null>(null);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [draft, setDraft] = useState<Query>({});
  const [query, setQuery] = useState<Query>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [revision, setRevision] = useState(0);
  const [name, setName] = useState("");
  const [alerts, setAlerts] = useState(false);
  const [replies, setReplies] = useState<Record<string,string>>({});
  const key = useRef<{ signature: string; value: string } | null>(null);
  const route = `/cabinet/${audience === "artist" ? "performer" : "venue"}/opportunities`;

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    const controller = new AbortController();
    void api<CommerceMe>("/me", { signal: controller.signal }).then((me) => {
      setOrg(me.organizations.find((o) => o.id === (getActiveOrg() || me.active_organization_id) && o.kind === audience) || me.organizations.find((o) => o.kind === audience) || null);
    }).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setReady(true); });
    return () => controller.abort();
  }, [audience]);
  useEffect(() => {
    if (!org) return;
    const controller = new AbortController(); setLoading(true); setError("");
    const params = new URLSearchParams(Object.fromEntries(Object.entries(query).map(([k,v]) => [k, String(v)])));
    void Promise.all([api<Feed>(`/organizations/${org.id}/opportunities?${params}`, { signal: controller.signal }), api<{ items: Saved[] }>(`/organizations/${org.id}/opportunity-filters`, { signal: controller.signal })])
      .then(([feed, searches]) => { setData(feed); setSaved(searches.items); })
      .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [org, query, revision]);
  const advanced = Boolean(data?.features["opportunities.filters"]);
  function change(field: string, value: string) { setDraft((prev) => { const next = { ...prev }; if (value) next[field] = field === "budget_min_rub" || field === "minimum_score" ? Number(value) : value; else delete next[field]; return next; }); }
  async function save(e: FormEvent) {
    e.preventDefault(); if (!org || busy) return;
    const params = { ...query }; delete params.page;
    const signature = JSON.stringify({ name, query: params, alerts });
    if (key.current?.signature !== signature) key.current = { signature, value: crypto.randomUUID() };
    setBusy("save"); setError("");
    try { await api(`/organizations/${org.id}/opportunity-filters`, { method: "POST", body: JSON.stringify({ name, query: params, instant_alerts: alerts, consent: alerts, idempotency_key: key.current.value }) }); key.current = null; setMessage("Поиск сохранён."); setRevision((r) => r + 1); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(""); }
  }
  async function respond(e: FormEvent, item: Opportunity) {
    e.preventDefault(); if (!org || busy) return;
    setBusy(item.id); setError("");
    try { await api(`/briefs/${item.id}/responses`, { method: "POST", body: JSON.stringify({ supplier_org_id: org.id, target_type: audience, target_id: item.match.profile_id, message: replies[item.id] || "" }) }); setMessage("Отклик отправлен заказчику."); setRevision((r) => r + 1); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(""); }
  }
  async function remove(id: string) {
    setBusy(id); setError("");
    try { await api(`/opportunity-filters/${id}`, { method: "DELETE" }); setRevision((r) => r + 1); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(""); }
  }
  return <main className="commerce-page"><p className="kicker">{org?.name || "Новые события"}</p><h1>Подходящие заказы</h1>
    <SupplyCabinetNav mode={audience === "artist" ? "performer" : "venue"} />
    <p>Заказы, которые подходят вашему профилю, географии и открытым датам. Отклики доступны и на Free.</p>
    {!ready && <p role="status">Загружаем рабочее пространство…</p>}
    {ready && !org && !error && <p className="empty"><Link href={getToken() ? "/profile" : loginHref(route)}>{getToken() ? "Создать рабочее пространство" : "Войти, чтобы увидеть подходящие заказы"}</Link></p>}
    {error && <div role="alert" className="card"><p>{error}</p><button className="btn secondary" onClick={() => { setQuery({}); setDraft({}); setRevision((r) => r + 1); }}>Повторить загрузку</button></div>}
    {message && <p role="status">{message}</p>}
    {loading && <p role="status">Сопоставляем брифы с вашим профилем…</p>}
    {org && data && <>
      <form className="card opportunity-filters" onSubmit={(e) => { e.preventDefault(); setQuery({ ...draft }); }}>
        <h2>Настроить поиск</h2>
        <label>Профиль<select value={draft.target_id || ""} onChange={(e) => change("target_id", e.target.value)}><option value="">Все мои профили</option>{data.profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <details><summary>Расширенные фильтры</summary><fieldset disabled={!advanced}><legend className="sr-only">Фильтры заказов</legend>
          <label>Город<input value={draft.city || ""} onChange={(e) => change("city", e.target.value)} maxLength={128} /></label>
          <label>Дата от<input type="date" value={draft.date_from || ""} onChange={(e) => change("date_from", e.target.value)} /></label>
          <label>Дата до<input type="date" value={draft.date_to || ""} onChange={(e) => change("date_to", e.target.value)} /></label>
          <label>Бюджет заказа от, ₽<input type="number" min={0} max={1000000000} value={draft.budget_min_rub ?? ""} onChange={(e) => change("budget_min_rub", e.target.value)} /></label>
          <label>Совпадение от, баллов<input type="number" min={0} max={100} value={draft.minimum_score ?? ""} onChange={(e) => change("minimum_score", e.target.value)} /></label>
        </fieldset></details>
        {!advanced && <p>Фильтры и сохранение поиска доступны в Pro и Premium. <Link href="/pricing">Сравнить тарифы</Link></p>}
        <div className="commerce-actions"><button className="btn" disabled={loading}>Применить</button><button className="btn secondary" type="button" onClick={() => { setDraft({}); setQuery({}); }}>Сбросить</button></div>
      </form>
      <details className="commerce-checkout"><summary>Сохранённые поиски и уведомления</summary>
        {advanced && isWriteRole(org.role) && <form onSubmit={save}><label>Название поиска<input required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} /></label><label className="commerce-actions"><input type="checkbox" checked={alerts} onChange={(e) => setAlerts(e.target.checked)} />Согласен получать уведомления в Букере о новых заказах по этому поиску</label><button className="btn secondary" disabled={!!busy}>Сохранить текущий поиск</button></form>}
        {saved.length ? <ul>{saved.map((item) => <li key={item.id}>{item.name}{item.instant_alerts ? " · уведомления включены" : ""}<div className="commerce-actions"><button className="btn secondary" disabled={!advanced} onClick={() => { setDraft(item.query); setQuery(item.query); }}>Открыть поиск</button><button className="btn secondary" disabled={!!busy} onClick={() => void remove(item.id)}>Удалить поиск</button></div></li>)}</ul> : <p>Сохранённых поисков пока нет.</p>}
      </details>
      {!loading && data.items.length === 0 && <div className="empty"><h2>Подходящих заказов пока нет</h2><p>{data.profiles.length ? "Проверьте открытые даты или измените фильтры." : "Создайте профиль и откройте календарь для сопоставления."}</p><Link href="/briefs">Все публичные брифы</Link></div>}
      {!loading && <div className="opportunity-list">{data.items.map((item) => <article className="card opportunity-card" aria-label={item.title} key={item.id}>
        <p className="kicker">{item.event_type_label} · {categoryLabel(item.role_needed)} · {item.city}</p><h2>{item.title}</h2>
        <p>{formatWhen(item.date_from)} — {formatWhen(item.date_to)} · {item.guest_count_band} гостей</p>
        <p>{item.budget_range ? `Бюджет: ${money(item.budget_range.min_rub)} — ${money(item.budget_range.max_rub)}` : "Бюджет не опубликован"}</p>
        <p className="opportunity-score">Совпадение <strong>{item.match.score}/100</strong> · {item.match.profile_name}</p>
        <ul className="opportunity-reasons">{item.match.reasons.map((reason) => <li key={reason.code}><span aria-hidden>{reason.state === "match" ? "✓" : "?"}</span> {reason.label}</li>)}</ul>
        {item.public_notes && <p>{item.public_notes}</p>}
        <details><summary>Как рассчитано совпадение</summary><p>{item.match.methodology}</p></details>
        {item.response_id ? <p className="chip ok">Отклик отправлен</p> : isWriteRole(org.role) && <form onSubmit={(e) => void respond(e, item)}><label>Ваше предложение<textarea value={replies[item.id] || ""} onChange={(e) => setReplies((previous) => ({ ...previous, [item.id]: e.target.value }))} required minLength={5} maxLength={4000} rows={3} /></label><p className="timeline">Это предварительный отклик. Цена и условия сделки согласуются в Deal Room.</p><button className="btn" disabled={!!busy}>Отправить предложение</button></form>}
      </article>)}</div>}
      {(data.page > 1 || data.has_more) && <nav className="commerce-actions" aria-label="Страницы заказов"><button disabled={data.page <= 1 || loading} onClick={() => setQuery((q) => ({ ...q, page: data.page - 1 }))}>Назад</button><span>Страница {data.page}</span><button disabled={!data.has_more || loading} onClick={() => setQuery((q) => ({ ...q, page: data.page + 1 }))}>Дальше</button></nav>}
    </>}
  </main>;
}
