"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError, getActiveOrg, getToken } from "@/lib/api";
import Link from "next/link";
import { loginHref } from "@/lib/next";
import { formatWhen } from "@/lib/format";

type Ticket = { id: string; ticket_number: string; category: string; subject: string; status: string; priority: boolean; created_at: string; body?: string };
type Queue = { items: Ticket[]; total: number; is_operator: boolean };
const CATEGORIES: Record<string, string> = { profile: "Профиль", brief: "Заявка", message: "Сообщения", review: "Отзыв", media: "Медиа", payment: "Оплата", technical: "Техническая проблема", other: "Другое" };
const errorText = (e: unknown) => e instanceof ApiError ? e.message : "Не удалось связаться с поддержкой. Повторите попытку.";

export default function SupportPage() {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [category, setCategory] = useState("other"); const [subject, setSubject] = useState(""); const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const [state, setState] = useState("all"); const [offset, setOffset] = useState(0); const [refresh, setRefresh] = useState(0);
  const [details, setDetails] = useState<Record<string, Ticket>>({}); const [detailBusy, setDetailBusy] = useState("");
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => { setSignedIn(Boolean(getToken())); }, []);
  useEffect(() => {
    if (!signedIn) return;
    const c = new AbortController(); setLoading(true);
    api<Queue>(`/support/tickets?state=${state}&offset=${offset}&limit=25`, { signal: c.signal })
      .then(data => { if (!c.signal.aborted) { setQueue(data); setError(""); } })
      .catch(e => { if (!c.signal.aborted) { setQueue(null); setError(errorText(e)); } })
      .finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [signedIn, state, offset, refresh]);
  async function onSubmit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    const payload = JSON.stringify({ organization_id: getActiveOrg() || undefined, category, subject: subject.trim(), body: body.trim() });
    if (pending.current?.fingerprint !== payload) pending.current = { fingerprint: payload, key: crypto.randomUUID() };
    try {
      const ticket = await api<Ticket>("/support/tickets", { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body: payload });
      pending.current = null; setSubject(""); setBody(""); setNotice(`${ticket.ticket_number}: обращение принято. ${ticket.priority ? "Приоритетная очередь." : "Обычная очередь."}`);
      setDetails({}); setOffset(0); setRefresh(v => v + 1);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function detail(id: string) { setDetailBusy(id); setError(""); try { const ticket = await api<Ticket>(`/support/tickets/${id}`); setDetails(v => ({ ...v, [id]: ticket })); } catch (e) { setError(errorText(e)); } finally { setDetailBusy(""); } }
  async function close(id: string) { setBusy(true); setError(""); try { await api(`/support/tickets/${id}/close`, { method: "POST" }); setNotice("Обращение закрыто."); setOffset(0); setRefresh(v => v + 1); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }
  if (signedIn === null) return <main><p role="status">Загрузка поддержки…</p></main>;
  if (!signedIn) return <main><p className="kicker">Букер</p><h1>Поддержка</h1><p><Link className="btn" href={loginHref("/support")}>Войти</Link></p></main>;
  return <main>
    <p className="kicker">Букер</p><h1>Поддержка и жалобы</h1>
    <p>Обращения рассматривает человек. Premium и Business дают приоритет в очереди по тарифу активной организации на момент отправки. Обычная поддержка доступна всем.</p>
    <p className="timeline">Срок ответа зависит от загрузки оператора. Приоритет не меняет правила сделки и рассмотрения споров.</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <form onSubmit={onSubmit} className="card commerce-checkout" aria-label="Новое обращение">
      <h2>Новое обращение</h2><p>Для выбора организации откройте <Link href="/profile">профиль</Link>.</p>
      <label className="commerce-org">Категория<select value={category} onChange={e => setCategory(e.target.value)} disabled={busy}>{Object.entries(CATEGORIES).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
      <label className="commerce-org">Тема<input value={subject} onChange={e => setSubject(e.target.value)} required minLength={3} maxLength={255} disabled={busy} /></label>
      <label className="commerce-org">Описание<textarea value={body} onChange={e => setBody(e.target.value)} required minLength={3} maxLength={8000} rows={5} disabled={busy} /></label>
      <button className="btn" type="submit" disabled={busy}>{busy ? "Отправка…" : "Отправить обращение"}</button>
    </form>
    <section className="card commerce-checkout" style={{ marginTop: 24 }} aria-label="Список обращений">
      <h2>{queue?.is_operator ? "Очередь оператора" : "Мои обращения"}</h2>
      {queue?.is_operator && <p>Открытые обращения идут первыми; внутри каждой очереди — сначала приоритетные, затем обычные, от старых к новым. Просмотр и закрытие записываются в журнал.</p>}
      <label className="commerce-org">Состояние обращений<select value={state} disabled={loading || busy} onChange={e => { setState(e.target.value); setOffset(0); }}><option value="all">Все</option><option value="open">Открытые</option><option value="closed">Закрытые</option></select></label>
      <button className="btn secondary" disabled={loading || busy} onClick={() => setRefresh(v => v + 1)}>Обновить обращения</button>
      {loading && <p role="status">Загрузка обращений…</p>}
      {queue && !loading && <><p>Найдено: {queue.total}.</p>{queue.items.length === 0 && <p>В этой выборке обращений пока нет.</p>}
        {queue.items.map(t => <article key={t.id} style={{ overflowWrap: "anywhere" }}>
          <h3>{t.subject}</h3><p>{t.ticket_number} · {CATEGORIES[t.category] || "Другое"} · {t.status === "closed" ? "Закрыто" : "Открыто"} · {t.priority ? "Приоритетная очередь" : "Обычная очередь"}</p><p className="timeline">{formatWhen(t.created_at)}</p>
          {details[t.id] ? <p style={{ whiteSpace: "pre-wrap" }}>{details[t.id].body}</p> : <button className="btn secondary" disabled={Boolean(detailBusy)} onClick={() => void detail(t.id)}>{detailBusy === t.id ? "Загрузка…" : `Прочитать ${t.ticket_number}`}</button>}
          {t.status !== "closed" && <p><button className="btn secondary" disabled={busy} onClick={() => void close(t.id)}>Закрыть {t.ticket_number}</button></p>}
        </article>)}
        <div className="commerce-actions">{offset > 0 && <button className="btn secondary" onClick={() => setOffset(v => Math.max(0, v - 25))}>Предыдущие обращения</button>}{offset + 25 < queue.total && <button className="btn secondary" onClick={() => setOffset(v => v + 25)}>Следующие обращения</button>}</div>
      </>}
    </section>
  </main>;
}
