"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
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
                <div>
                  <strong>{h.name}</strong>
                  <p className="timeline">Вместимость: {h.capacity} гостей</p>
                </div>
                <div className="dashboard-action-meta">
                  <span className="chip chip-glass">Зал</span>
                  <Link className="btn secondary" href={`/venues/${venueId}`}>
                    Витрина
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
    </DashboardWidget>
  );
}
