"use client";

import { FormEvent, useMemo, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import { DashboardWidget } from "../../DashboardWidget";
import type { VenueHallTarget } from "../types";

type Props = {
  halls: VenueHallTarget[];
  role: string;
  onChanged?: () => void;
};

export function VenueHallsWidget({ halls, role, onChanged }: Props) {
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("100");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canManage = isWriteRole(role);

  const venueId = useMemo(() => {
    const withVenue = halls.find((h) => h.venue_id);
    return withVenue?.venue_id || "";
  }, [halls]);

  const realHalls = halls.filter((h) => h.resource_type === "hall");

  async function addHall(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !venueId) {
      setError("Сначала создайте площадку в блоке «Свободные слоты».");
      return;
    }
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
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить зал");
    } finally {
      setBusy(false);
    }
  }

  return (
    <DashboardWidget
      title="Залы"
      hint="Каждый зал — отдельный календарь и слоты"
      accent="venue"
      span="half"
      isEmpty={realHalls.length === 0 && !canManage}
      empty="Залы ещё не заведены."
    >
      {realHalls.length > 0 ? (
        <ul className="dashboard-list">
          {realHalls.map((h) => (
            <li key={h.resource_id}>
              <article className="dashboard-action-card hall-card">
                <div>
                  <strong>{h.label}</strong>
                  <p className="timeline">Отдельный ресурс для бронирования</p>
                </div>
                <span className="chip live">Зал</span>
              </article>
            </li>
          ))}
        </ul>
      ) : (
        <p className="timeline">Пока нет залов — добавьте первый ниже.</p>
      )}
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
          <button type="submit" disabled={busy || !venueId}>
            {busy ? "Добавляем…" : "Добавить зал"}
          </button>
        </form>
      ) : null}
    </DashboardWidget>
  );
}
