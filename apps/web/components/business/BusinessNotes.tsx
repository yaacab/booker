"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { eventCommandKey, eventCommandSeed } from "@/lib/eventCommands";
import { formatWhen } from "@/lib/format";

type Note = { id: string; body: string; revision: number; author_name: string; created_at: string; can_edit: boolean; can_delete: boolean };
type Notes = { items: Note[]; total: number; can_write: boolean };
export function BusinessNotes({ eventId }: { eventId: string }) {
  const [data, setData] = useState<Notes | null>(null); const [offset, setOffset] = useState(0); const [refresh, setRefresh] = useState(0);
  const [body, setBody] = useState(""); const [editing, setEditing] = useState<Note | null>(null); const [edited, setEdited] = useState("");
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const url = `/business/events/${eventId}/notes`;
  useEffect(() => { const c = new AbortController(); setLoading(true); api<Notes>(`${url}?offset=${offset}`, { signal: c.signal }).then(value => { if (!c.signal.aborted) { setData(value); setError(""); } }).catch(e => { if (!c.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!c.signal.aborted) setLoading(false); }); return () => c.abort(); }, [url, offset, refresh]);
  async function write(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(""); try { const payload = { body: body.trim() }; const storageKey = `business-note:${eventId}`; const key = await eventCommandKey(eventCommandSeed(storageKey), payload); await api(url, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(payload) }); sessionStorage.removeItem(storageKey); setBody(""); setOffset(0); setRefresh(v => v + 1); } catch(e) { setError(commerceError(e)); } finally { setBusy(false); } }
  async function change(note: Note, remove: boolean) { setBusy(true); setError(""); try { await api(`/business/notes/${note.id}${remove ? `?expected_revision=${note.revision}` : ""}`, { method: remove ? "DELETE" : "PUT", ...(remove ? {} : { body: JSON.stringify({ body: edited, expected_revision: note.revision }) }) }); setEditing(null); setRefresh(v => v + 1); } catch(e) { setError(commerceError(e)); } finally { setBusy(false); } }
  if (!loading && data && !data.can_write && !data.total && !error) return null;
  return <section className="card commerce-checkout" aria-label="Внутренние заметки команды"><h2>Внутренние заметки команды</h2><p>Видны только участникам вашей организации. Они не отправляются исполнителям и не меняют условия сделок.</p>
    {loading && <p role="status">Загружаем заметки…</p>}{error && <p role="alert">{error}</p>}
    {data?.can_write && <form onSubmit={e => void write(e)}><div className="commerce-org"><label htmlFor={`note-new-${eventId}`}>Новая внутренняя заметка</label><textarea id={`note-new-${eventId}`} required maxLength={4000} value={body} onChange={e => setBody(e.target.value)} /></div><button className="btn" disabled={busy || loading || !body.trim()}>Добавить заметку</button></form>}
    {data && !data.total && <p>Заметок пока нет.</p>}
    {data?.items.map(note => <article key={note.id} style={{ borderTop: "1px solid var(--line)", paddingTop: "1rem", marginTop: "1rem", overflowWrap: "anywhere" }}><p className="timeline">{note.author_name} · {formatWhen(note.created_at)}</p>
      {editing?.id === note.id ? <form onSubmit={e => { e.preventDefault(); void change(editing, false); }}><div className="commerce-org"><label htmlFor={`note-edit-${note.id}`}>Текст заметки</label><textarea id={`note-edit-${note.id}`} required maxLength={4000} value={edited} onChange={e => setEdited(e.target.value)} /></div><div className="commerce-actions"><button className="btn" disabled={busy || !edited.trim()}>Сохранить заметку</button><button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Отмена</button></div></form> : <><p style={{ whiteSpace: "pre-wrap" }}>{note.body}</p><div className="commerce-actions">{note.can_edit && <button className="btn secondary" type="button" disabled={busy || loading} onClick={() => { setEditing(note); setEdited(note.body); }}>Изменить заметку</button>}{note.can_delete && <button className="btn secondary" type="button" disabled={busy || loading} onClick={() => void change(note, true)}>Удалить заметку</button>}</div></>}
    </article>)}
    <div className="commerce-actions" style={{ marginTop: "1rem" }}><button className="btn secondary" type="button" disabled={busy || loading} onClick={() => setRefresh(v => v + 1)}>Обновить заметки</button>{offset > 0 && <button className="btn secondary" type="button" disabled={busy || loading} onClick={() => setOffset(v => Math.max(0, v - 50))}>Новые заметки</button>}{data && offset + 50 < data.total && <button className="btn secondary" type="button" disabled={busy || loading} onClick={() => setOffset(v => v + 50)}>Старые заметки</button>}</div>
  </section>;
}
