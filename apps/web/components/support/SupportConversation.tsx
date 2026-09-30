"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatWhen } from "@/lib/format";

type Messages = { items: { id: string; author_role: string; body: string; created_at: string }[]; total: number; can_reply: boolean };
export function SupportConversation({ ticketId, closed }: { ticketId: string; closed: boolean }) {
  const [data, setData] = useState<Messages | null>(null); const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [offset, setOffset] = useState(0); const [refresh, setRefresh] = useState(0); const [notice, setNotice] = useState("");
  const pending = useRef<{ body: string; key: string } | null>(null);
  useEffect(() => {
    const c = new AbortController(); setLoading(true);
    api<Messages>(`/support/tickets/${ticketId}/messages?offset=${offset}&limit=50`, { signal: c.signal })
      .then(result => { if (!c.signal.aborted) { setData(result); setError(""); } })
      .catch(e => { if (!c.signal.aborted) { setData(null); setError(e instanceof ApiError ? e.message : "Не удалось загрузить переписку"); } })
      .finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [ticketId, offset, refresh]);
  async function send(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    const text = body.trim();
    if (pending.current?.body !== text) pending.current = { body: text, key: crypto.randomUUID() };
    try {
      await api(`/support/tickets/${ticketId}/messages`, { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body: JSON.stringify({ body: text }) });
      pending.current = null; setBody(""); setNotice("Сообщение сохранено."); setOffset(0); setRefresh(v => v + 1);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Не удалось отправить ответ. Повторите попытку."); } finally { setBusy(false); }
  }
  return <section aria-label="Переписка по обращению" className="commerce-checkout">
    <h4>Переписка с поддержкой</h4>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{loading && <p role="status">Загрузка переписки…</p>}
    {data && <>{data.items.length === 0 && <p>Ответов пока нет.</p>}
      <ol style={{ paddingLeft: "1.25rem" }}>{data.items.map(message => <li key={message.id} style={{ marginBottom: "1rem", overflowWrap: "anywhere" }}><p><strong>{message.author_role === "operator" ? "Оператор поддержки" : "Автор обращения"}</strong> · {formatWhen(message.created_at)}</p><p style={{ whiteSpace: "pre-wrap" }}>{message.body}</p></li>)}</ol>
      <div className="commerce-actions">{offset + 50 < data.total && <button className="btn secondary" disabled={loading || busy} onClick={() => setOffset(v => v + 50)}>Более ранние ответы</button>}{offset > 0 && <button className="btn secondary" disabled={loading || busy} onClick={() => setOffset(v => Math.max(0, v - 50))}>Более новые ответы</button>}</div>
      {closed || !data.can_reply ? <p>Обращение закрыто. Переписка сохранена; новый вопрос можно отправить отдельным обращением.</p> : <form onSubmit={send} className="commerce-checkout"><label className="commerce-org">Ваш ответ<textarea value={body} onChange={e => setBody(e.target.value)} rows={4} required maxLength={8000} disabled={busy} /></label><button className="btn" disabled={busy || !body.trim()}>{busy ? "Отправка ответа…" : "Отправить ответ"}</button></form>}
    </>}
    <button className="btn secondary" disabled={loading || busy} onClick={() => { setOffset(0); setRefresh(v => v + 1); }}>Обновить переписку</button>
  </section>;
}
