"use client";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { CompatibilityResult, type CompatibilityData } from "./CompatibilityResult";

type Candidate = { id: string; name: string };
function localInput(value: string) { return new Date(new Date(value).getTime() + 3 * 3600000).toISOString().slice(0, 16); }

export function CompatibilityTool() {
  const [city, setCity] = useState("Москва"); const [artists, setArtists] = useState<Candidate[]>([]); const [venues, setVenues] = useState<Candidate[]>([]);
  const [artist, setArtist] = useState(""); const [venue, setVenue] = useState(""); const [hall, setHall] = useState(""); const [halls, setHalls] = useState<Candidate[]>([]);
  const [eventId, setEventId] = useState(""); const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const [guests, setGuests] = useState("");
  const [data, setData] = useState<CompatibilityData | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search); setArtist(q.get("artist") || ""); setVenue(q.get("venue") || ""); setEventId(q.get("event") || "");
    if (q.get("date")) { setStart(`${q.get("date")}T18:00`); setEnd(`${q.get("date")}T22:00`); }
  }, []);
  useEffect(() => {
    const controller = new AbortController(); const timer = window.setTimeout(() => {
      setLoading(true); setError("");
      void api<{ items: Candidate[]; venues: Candidate[] }>(`/catalog/search?city=${encodeURIComponent(city)}`, { signal: controller.signal }).then((res) => { setArtists(res.items); setVenues(res.venues); })
        .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [city, revision]);
  useEffect(() => {
    if (!artist) return;
    const controller = new AbortController(); void api<Candidate>(`/artists/${artist}`, { signal: controller.signal }).then((profile) => setArtists((items) => items.some((p) => p.id === profile.id) ? items : [profile, ...items])).catch(() => {});
    return () => controller.abort();
  }, [artist, loading]);
  useEffect(() => {
    setHalls([]); setHall(""); if (!venue) return;
    const controller = new AbortController();
    void Promise.all([api<Candidate>(`/venues/${venue}`, { signal: controller.signal }), api<{ items: Candidate[] }>(`/venues/${venue}/halls`, { signal: controller.signal })]).then(([profile, rooms]) => { setVenues((items) => items.some((p) => p.id === profile.id) ? items : [profile, ...items]); setHalls(rooms.items); if (rooms.items.length === 1) setHall(rooms.items[0].id); })
      .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    return () => controller.abort();
  }, [venue, loading]);
  useEffect(() => {
    if (!eventId) return;
    const controller = new AbortController();
    void api<{ event_date: string; guest_count: number; city: string; ends_at?: string }>(`/events/${eventId}`, { signal: controller.signal }).then((ev) => { setStart(localInput(ev.event_date)); setGuests(String(ev.guest_count)); setCity(ev.city); if (ev.ends_at) setEnd(localInput(ev.ends_at)); })
      .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    return () => controller.abort();
  }, [eventId]);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setData(null);
    try { const result = await api<CompatibilityData>("/compatibility", { method: "POST", body: JSON.stringify({ artist_id: artist, venue_id: venue, hall_id: hall || undefined, event_id: eventId || undefined, starts_at: start ? `${start}:00+03:00` : undefined, ends_at: end ? `${end}:00+03:00` : undefined, guest_count: guests ? Number(guests) : undefined }) }); setData(result); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  return <main className="commerce-page"><p className="kicker">До подтверждения условий</p><h1>Совместимость</h1><p>Сопоставьте требования артиста, оснащение зала и временные окна. Неизвестные параметры потребуют уточнения.</p>
    {error && <div className="card" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision((r) => r + 1)}>Повторить загрузку</button></div>}
    {loading && <p role="status">Загружаем профили…</p>}
    <form className="card compatibility-form" onSubmit={submit} aria-label="Параметры совместимости"><div className="grid">
      <label>Город<input value={city} onChange={(e) => { setCity(e.target.value); setData(null); }} /></label>
      <label>Артист<select required value={artist} onChange={(e) => { setArtist(e.target.value); setData(null); }}><option value="">Выберите артиста</option>{artists.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <label>Площадка<select required value={venue} onChange={(e) => { setVenue(e.target.value); setData(null); }}><option value="">Выберите площадку</option>{venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
      <label>Зал<select value={hall} onChange={(e) => { setHall(e.target.value); setData(null); }}><option value="">Зал пока не выбран</option>{halls.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</select></label>
      <label>Начало, по Москве<input type="datetime-local" value={start} disabled={Boolean(eventId)} required={Boolean(end)} onChange={(e) => { setStart(e.target.value); setData(null); }} /></label>
      <label>Окончание, по Москве<input type="datetime-local" value={end} required={Boolean(start)} min={start || undefined} onChange={(e) => { setEnd(e.target.value); setData(null); }} /></label>
      <label>Гостей<input type="number" min={1} max={100000} value={guests} disabled={Boolean(eventId)} onChange={(e) => { setGuests(e.target.value); setData(null); }} /></label>
    </div><p className="timeline">Время здесь используется для проверки и не меняет дату или бронирование. Без времени доступность останется неизвестной.</p>
    {!loading && (!artists.length || !venues.length) && <p className="empty">В этом городе пока недостаточно опубликованных профилей для проверки пары.</p>}
    <button disabled={busy || loading || !artists.some((a) => a.id === artist) || !venues.some((v) => v.id === venue)} className="btn">{busy ? "Проверяем…" : "Проверить совместимость"}</button></form>
    {busy && <p role="status">Сопоставляем параметры и календари…</p>}{data && <CompatibilityResult data={data} />}
  </main>;
}
