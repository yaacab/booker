"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import { DashboardWidget } from "../../DashboardWidget";

type CalendarTarget = { resource_type: string; resource_id: string; label: string };

type OpenSlotsWidgetProps = {
  orgId: string;
  role: string;
  orgName?: string;
  supplyKind?: "artist" | "venue";
};

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

  const slotTargets = useMemo(
    () => targets.filter((t) => t.resource_type === "artist" || t.resource_type === "hall"),
    [targets],
  );
  const target = slotTargets.find((t) => t.resource_id === targetId) || slotTargets[0] || null;
  const canManage = isWriteRole(role);

  async function reloadTargets() {
    const res = await api<{ items: CalendarTarget[] }>(
      `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
    );
    setTargets(res.items);
    const firstSlot = res.items.find((t) => t.resource_type === "artist" || t.resource_type === "hall");
    if (firstSlot) setTargetId(firstSlot.resource_id);
  }

  useEffect(() => {
    if (!orgId) return;
    void reloadTargets().catch(() => setTargets([]));
  }, [orgId]);

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
      setError("Сначала создайте профиль в каталоге.");
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
        try {
          await api("/slots", {
            method: "POST",
            body: JSON.stringify({
              resource_type: target.resource_type,
              resource_id: target.resource_id,
              starts_at: eveningIso(day, 18),
              ends_at: eveningIso(day, 22),
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
          ? `Открыто свободных вечеров: ${created}${skipped ? ` · уже занято: ${skipped}` : ""}.`
          : skipped
            ? "На этот период слоты уже есть."
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
      hint={
        supplyKind === "venue"
          ? "Залы без открытых дат не попадают в поиск заказчика."
          : "Без открытых дат вас нет в поиске. Заказчик бронирует ваш вечер."
      }
      accent={supplyKind === "venue" ? "venue" : "performer"}
      span="full"
      isEmpty={!canManage && slotTargets.length === 0}
      empty="Календарь настраивает владелец или менеджер."
    >
      {!canManage ? (
        <p className="timeline">Только просмотр: слоты открывает менеджер.</p>
      ) : slotTargets.length === 0 ? (
        <div className="cabinet-inline-form">
          <p className="timeline">
            Чтобы открыть даты, нужен профиль в каталоге. Один шаг — и можно публиковать свободные вечера.
          </p>
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          {result ? <p className="timeline">{result}</p> : null}
          <button type="button" disabled={busy} onClick={() => void ensureCatalogProfile()}>
            {busy ? "Создаём…" : supplyKind === "venue" ? "Создать площадку в каталоге" : "Создать профиль в каталоге"}
          </button>
        </div>
      ) : (
        <form className="cabinet-inline-form" onSubmit={(e) => void openSlots(e)}>
          {slotTargets.length > 1 ? (
            <label>
              Календарь
              <select value={target?.resource_id || ""} onChange={(e) => setTargetId(e.target.value)}>
                {slotTargets.map((t) => (
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
            Ближайшие вечера 18:00–22:00 МСК
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
