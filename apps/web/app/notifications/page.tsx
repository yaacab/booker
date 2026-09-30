"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, getToken } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { loginHref } from "@/lib/next";

type Inbox = { items: { id: string; subject: string; body: string; created_at: string; read_at: string | null; href: string | null }[]; total: number; unread_count: number };
export default function NotificationsPage() {
  const [authed, setAuthed] = useState<boolean | null>(null); const [data, setData] = useState<Inbox | null>(null);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(""); const [error, setError] = useState("");
  const [unread, setUnread] = useState(false); const [offset, setOffset] = useState(0); const [refresh, setRefresh] = useState(0);
  useEffect(() => setAuthed(Boolean(getToken())), []);
  useEffect(() => {
    if (!authed) return;
    const c = new AbortController(); setLoading(true);
    api<Inbox>(`/notifications?limit=25&offset=${offset}&unread_only=${unread}`, { signal: c.signal })
      .then(res => { if (!c.signal.aborted) { setData(res); setError(""); } })
      .catch(e => { if (!c.signal.aborted) { setData(null); setError(e instanceof ApiError ? e.message : "Не удалось загрузить уведомления"); } })
      .finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [authed, offset, unread, refresh]);
  async function mark(id: string) { setBusy(id); setError(""); try { await api(`/notifications/${id}/read`, { method: "POST" }); setRefresh(v => v + 1); window.dispatchEvent(new Event("booker:inbox-changed")); } catch (e) { setError(e instanceof ApiError ? e.message : "Не удалось отметить уведомление"); } finally { setBusy(""); } }
  if (authed === null) return <main><p role="status">Загрузка уведомлений…</p></main>;
  if (!authed) return <main><h1>Уведомления</h1><Link className="btn" href={loginHref("/notifications")}>Войти</Link></main>;
  return <main><p className="kicker">Букер</p><h1>Уведомления</h1>
    <section className="card commerce-checkout" aria-label="Входящие уведомления">
      <label style={{ display: "flex", alignItems: "center", gap: 10 }}><input style={{ width: 20, height: 20, minHeight: 20, margin: 0, flexShrink: 0 }} type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setOffset(0); }} /> Только непрочитанные</label>
      <button className="btn secondary" disabled={loading || Boolean(busy)} onClick={() => setRefresh(v => v + 1)}>Обновить уведомления</button>
      {error && <p role="alert">{error}</p>}{loading && <p role="status">Загрузка уведомлений…</p>}
      {data && !loading && <><p>Непрочитанных: {data.unread_count}. В выборке: {data.total}.</p>{data.items.length === 0 && <p>Уведомлений в этой выборке пока нет.</p>}
        {data.items.map(item => <article key={item.id} style={{ overflowWrap: "anywhere", marginTop: "1rem" }}><h2>{item.subject || "Уведомление"}</h2><p className="timeline">{formatWhen(item.created_at)} · {item.read_at ? "Прочитано" : "Новое"}</p><p style={{ whiteSpace: "pre-wrap" }}>{item.body}</p><div className="commerce-actions">{item.href && <Link className="btn secondary" href={item.href}>Открыть</Link>}{!item.read_at && <button className="btn" disabled={Boolean(busy)} onClick={() => void mark(item.id)}>{busy === item.id ? "Сохраняем…" : "Отметить прочитанным"}</button>}</div></article>)}
        <div className="commerce-actions">{offset > 0 && <button className="btn secondary" onClick={() => setOffset(v => Math.max(0, v - 25))}>Предыдущие уведомления</button>}{offset + 25 < data.total && <button className="btn secondary" onClick={() => setOffset(v => v + 25)}>Следующие уведомления</button>}</div>
      </>}
    </section>
  </main>;
}
