"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { VenueHall } from "../types";

type Props = {
  venueId: string;
  venueName?: string;
  role: string;
};

export function VenueHallsPanel({ venueId, venueName, role }: Props) {
  const [halls, setHalls] = useState<VenueHall[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("100");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canManage = isWriteRole(role);
  const [editing, setEditing] = useState<string | null>(null);
  const [tariffs, setTariffs] = useState<{ id: string; title: string; honorarium_rub: number }[]>([]);
  const [tariffEditing, setTariffEditing] = useState<string | null>(null);

  const loadTariffs = useCallback(async () => {
    if (!venueId) return;
    try {
      const v = await api<{ tariffs?: { id: string; title: string; honorarium_rub: number }[] }>(`/venues/${encodeURIComponent(venueId)}`);
      setTariffs(v.tariffs || []);
    } catch {
      setTariffs([]);
    }
  }, [venueId]);
  useEffect(() => { void loadTariffs(); }, [loadTariffs]);

  async function run(action: () => Promise<unknown>, after: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await after();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить");
      return false;
    } finally {
      setBusy(false);
    }
  }
  const base = `/venues/${encodeURIComponent(venueId)}`;

  const loadHalls = useCallback(async () => {
    if (!venueId) {
      setHalls([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await api<{ items: VenueHall[] }>(
        `/venues/${encodeURIComponent(venueId)}/halls`,
      );
      setHalls(res.items || []);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить залы");
    } finally {
      setLoading(false);
    }
  }, [venueId]);

  useEffect(() => {
    void loadHalls();
  }, [loadHalls]);

  async function addHall(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !venueId) return;
    const title = name.trim();
    if (!title) {
      setError("Укажите название зала");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api(`/venues/${encodeURIComponent(venueId)}/halls`, {
        method: "POST",
        body: JSON.stringify({
          name: title,
          capacity: Number(capacity) || 100,
        }),
      });
      trackClientEvent("cabinet.hall_created", { venue_id: venueId });
      setName("");
      await loadHalls();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить зал");
    } finally {
      setBusy(false);
    }
  }

  if (!venueId) {
    return (
      <DashboardWidget
        title="Залы площадки"
        hint="Управление через /venues/{id}/halls"
        accent="venue"
        span="full"
        isEmpty
        empty="Сначала создайте площадку в блоке «Свободные слоты» на календаре."
      />
    );
  }

  return (
    <DashboardWidget
      title="Залы площадки"
      hint={
        venueName
          ? `${venueName} — каждый зал со своим календарём`
          : "Каждый зал — отдельный ресурс календаря"
      }
      accent="venue"
      span="full"
      isEmpty={!loading && halls.length === 0 && !canManage}
      empty="Залы ещё не заведены."
    >
      {loading ? <p className="timeline">Загружаем залы…</p> : null}
      {!loading && halls.length > 0 ? (
        <ul className="dashboard-list">
          {halls.map((h) => (
            <li key={h.id}>
              <article className="dashboard-action-card hall-card">
                {editing === h.id ? (
                  <form className="cabinet-inline-form" onSubmit={async (e) => { e.preventDefault(); const d = new FormData(e.currentTarget); if (await run(() => api(`${base}/halls/${encodeURIComponent(h.id)}`, { method: "PATCH", body: JSON.stringify({ name: String(d.get("name") || "").trim(), capacity: Number(d.get("capacity") || 0) }) }), loadHalls)) setEditing(null); }}>
                    <label>Название<input name="name" defaultValue={h.name} required /></label>
                    <label>Вместимость<input name="capacity" type="number" min={1} defaultValue={h.capacity} required /></label>
                    <button type="submit" disabled={busy}>Сохранить</button>
                    <button type="button" className="secondary" onClick={() => setEditing(null)}>Отмена</button>
                  </form>
                ) : (
                  <div>
                    <strong>{h.name}</strong>
                    <p className="timeline">Вместимость: {h.capacity} гостей</p>
                    {canManage ? <p><button type="button" className="linkish" onClick={() => setEditing(h.id)}>Изменить</button> <button type="button" className="linkish" disabled={busy} onClick={() => { if (window.confirm(`Удалить зал «${h.name}»? Свободные даты зала тоже удалятся.`)) void run(() => api(`${base}/halls/${encodeURIComponent(h.id)}`, { method: "DELETE" }), loadHalls); }}>Удалить</button></p> : null}
                  </div>
                )}
                <div className="dashboard-action-meta">
                  <span className="chip chip-glass">Зал</span>
                  <Link className="btn secondary" href={`/venues/${venueId}`}>
                    Витрина
                  </Link>
                  <Link className="btn secondary" href={`/venues/${venueId}/share`}>
                    Поделиться / QR
                  </Link>
                </div>
              </article>
            </li>
          ))}
        </ul>
      ) : null}
      {!loading && halls.length === 0 ? (
        <p className="timeline">Пока нет залов — добавьте первый ниже.</p>
      ) : null}
      {canManage ? (
        <form className="cabinet-inline-form" onSubmit={(e) => void addHall(e)}>
          <label>
            Новый зал
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Основной зал, Loft, Терраса…"
              required
            />
          </label>
          <label>
            Вместимость
            <input
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </label>
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={busy}>
            {busy ? "Добавляем…" : "Добавить зал"}
          </button>
        </form>
      ) : null}
      <section className="venue-tariffs" aria-labelledby="venue-tariffs-heading">
        <h3 id="venue-tariffs-heading">Стоимость аренды</h3>
        <p className="timeline">Эта цена подставится в предложение по заявке — её можно изменить для каждой заявки. Без тарифа заказчик видит «Цена по запросу».</p>
        {tariffs.length ? <ul className="dashboard-list">{tariffs.map((t) => <li key={t.id}>
          {tariffEditing === t.id ? (
            <form className="cabinet-inline-form" onSubmit={async (e) => { e.preventDefault(); const d = new FormData(e.currentTarget); if (await run(() => api(`${base}/tariffs/${encodeURIComponent(t.id)}`, { method: "PATCH", body: JSON.stringify({ title: String(d.get("title") || "").trim(), honorarium_rub: Number(d.get("amount") || 0) }) }), loadTariffs)) setTariffEditing(null); }}>
              <label>Название<input name="title" defaultValue={t.title} required /></label>
              <label>Стоимость, ₽<input name="amount" type="number" min={1} defaultValue={t.honorarium_rub} required /></label>
              <button type="submit" disabled={busy}>Сохранить</button>
              <button type="button" className="secondary" onClick={() => setTariffEditing(null)}>Отмена</button>
            </form>
          ) : <span>{t.title} · {money(t.honorarium_rub)}{canManage ? <> <button type="button" className="linkish" onClick={() => setTariffEditing(t.id)}>Изменить</button> <button type="button" className="linkish" disabled={busy} onClick={() => { if (window.confirm(`Удалить тариф «${t.title}»?`)) void run(() => api(`${base}/tariffs/${encodeURIComponent(t.id)}`, { method: "DELETE" }), loadTariffs); }}>Удалить</button></> : null}</span>}
        </li>)}</ul> : <p className="timeline">Тарифов пока нет.</p>}
        {canManage ? <form className="cabinet-inline-form" onSubmit={async (e) => { e.preventDefault(); const f = e.currentTarget; const d = new FormData(f); const title = String(d.get("title") || "").trim(); const amount = Number(d.get("amount") || 0); if (!title || !(amount > 0)) { setError("Укажите название тарифа и стоимость больше нуля"); return; } if (await run(() => api(`${base}/tariffs`, { method: "POST", body: JSON.stringify({ title, honorarium_rub: amount }) }), loadTariffs)) f.reset(); }}>
          <label>Тариф<input name="title" placeholder="Вечер до 23:00" required /></label>
          <label>Стоимость, ₽<input name="amount" type="number" min={1} required /></label>
          <button type="submit" disabled={busy}>Добавить тариф</button>
        </form> : null}
      </section>
    </DashboardWidget>
  );
}
