"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import { DashboardWidget } from "../../DashboardWidget";

type CalendarTarget = { resource_type: string; resource_id: string; label: string };

type OpenSlotsWidgetProps = {
  orgId: string;
  role: string;
  orgName?: string;
  /** artist → POST /artists; venue → POST /venues (+ hall) */
  supplyKind?: "artist" | "venue";
};

/** Moscow evening window as ISO with +03:00 (API stores aware datetimes). */
function eveningIso(day: string, hour: number, minute = 0): string {
  const hh = String(hour).padStart(2, "0");
  const mm = String(minute).padStart(2, "0");
  return `${day}T${hh}:${mm}:00+03:00`;
}

function addDaysIso(from: Date, days: number): string {
  const d = new Date(from);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function OpenSlotsWidget({ orgId, role, orgName, supplyKind = "artist" }: OpenSlotsWidgetProps) {
  const [targets, setTargets] = useState<CalendarTarget[]>([]);
  const [targetId, setTargetId] = useState("");
  const [days, setDays] = useState(14);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");

  async function reloadTargets() {
    const res = await api<{ items: CalendarTarget[] }>(
      `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
    );
    setTargets(res.items);
    if (res.items[0]) setTargetId(res.items[0].resource_id);
  }

  useEffect(() => {
    if (!orgId) return;
    void reloadTargets().catch(() => setTargets([]));
  }, [orgId]);

  const canManage = isWriteRole(role);
  const target = targets.find((t) => t.resource_id === targetId) || targets[0];

  async function ensureCatalogProfile() {
    setBusy(true);
    setError("");
    try {
      if (supplyKind === "venue") {
        await api("/venues", {
          method: "POST",
          body: JSON.stringify({
            organization_id: orgId,
            name: (orgName || "Площадка").trim() || "Площадка",
            city: "Москва",
            capacity: 100,
          }),
        });
      } else {
        await api("/artists", {
          method: "POST",
          body: JSON.stringify({
            organization_id: orgId,
            name: (orgName || "Исполнитель").trim() || "Исполнитель",
            city: "Москва",
            category: "dj",
          }),
        });
      }
      await reloadTargets();
      setResult("Профиль в каталоге создан — можно открывать свободные слоты.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать профиль");
    } finally {
      setBusy(false);
    }
  }

  async function openSlots(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !target) {
      setError("Нет календаря исполнителя — сначала создайте профиль в каталоге (услуга / артист).");
      return;
    }
    setBusy(true);
    setError("");
    setResult("");
    const today = new Date();
    let created = 0;
    let skipped = 0;
    try {
      for (let i = 1; i <= days; i++) {
        const day = addDaysIso(today, i);
        const starts_at = eveningIso(day, 18);
        const ends_at = eveningIso(day, 22);
        try {
          await api("/slots", {
            method: "POST",
            body: JSON.stringify({
              resource_type: target.resource_type,
              resource_id: target.resource_id,
              starts_at,
              ends_at,
            }),
          });
          created += 1;
        } catch {
          skipped += 1;
        }
      }
      trackClientEvent("cabinet.slots_opened", { created, skipped, days });
      setResult(
        created > 0
          ? `Открыто свободных вечеров: ${created}${skipped ? ` · пропущено (уже занято): ${skipped}` : ""}. Вас увидят в каталоге на эти даты.`
          : skipped
            ? "На выбранный период слоты уже есть или пересекаются — новые не добавлены."
            : "Не удалось открыть слоты.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось открыть слоты");
    } finally {
      setBusy(false);
    }
  }

  if (!orgId) return null;

  return (
    <DashboardWidget
      title="Свободные слоты"
      hint="Без открытых дат вас нет в поиске. Заказчик бронирует ваш вечер — не вы ищете событие."
      isEmpty={!canManage && targets.length === 0}
      empty="Календарь настраивает владелец или менеджер профиля."
    >
      {!canManage ? (
        <p className="timeline">Только просмотр: слоты открывает менеджер.</p>
      ) : targets.length === 0 ? (
        <div style={{ display: "grid", gap: 12 }}>
          <p className="timeline">
            Чтобы открыть даты, нужен профиль в каталоге. Создайте его одним шагом — потом откроете свободные вечера.
          </p>
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          {result ? <p className="timeline">{result}</p> : null}
          <button type="button" disabled={busy} onClick={() => void ensureCatalogProfile()}>
            {busy ? "Создаём…" : "Создать профиль в каталоге"}
          </button>
        </div>
      ) : (
        <form className="dashboard-list" style={{ display: "grid", gap: 12 }} onSubmit={(e) => void openSlots(e)}>
          {targets.length > 1 ? (
            <label>
              Кому открыть даты
              <select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                {targets.map((t) => (
                  <option key={t.resource_id} value={t.resource_id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="timeline">Календарь: {target?.label}</p>
          )}
          <label>
            Открыть ближайшие вечера (18:00–22:00 МСК)
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={7}>7 дней</option>
              <option value={14}>14 дней</option>
              <option value={30}>30 дней</option>
            </select>
          </label>
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          {result ? <p className="timeline">{result}</p> : null}
          <button type="submit" disabled={busy}>
            {busy ? "Открываем…" : "Открыть свободные слоты"}
          </button>
        </form>
      )}
    </DashboardWidget>
  );
}
