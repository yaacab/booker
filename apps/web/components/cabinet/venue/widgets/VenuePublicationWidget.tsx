"use client";

import { FormEvent } from "react";
import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";
import { useVenueProfile } from "../useVenueProfile";

const REASON_LABELS: Record<string, string> = {
  publication_enabled: "Публичная карточка выключена",
  verified: "Нужна верификация администратором",
  moderation: "Нужна модерация площадки",
  claimed: "Площадка ещё не подтверждена владельцем",
  halls: "Добавьте хотя бы один зал",
  tariff: "Добавьте тариф с ценой",
  media: "Подтвердите фото и права",
  representative: "Нужен представитель owner/admin",
  calendar_30d: "Подтвердите календарь минимум на 30 дней",
  calendar_entries: "Добавьте актуальные записи в календарь",
};

type Props = { venueId: string; role: string; onChanged?: () => void };

export function VenuePublicationWidget({ venueId, role, onChanged }: Props) {
  const {
    profile,
    loading,
    busy,
    error,
    canManage,
    publicHref,
    saveCalendarEvidence,
    setPublicationEnabled,
  } = useVenueProfile(venueId, role);

  async function onEvidence(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const ok = await saveCalendarEvidence(Number(data.get("calendar_days") || 90));
    if (ok) onChanged?.();
  }

  const reasons = (profile?.publication_reason_codes || []).map(
    (code) => REASON_LABELS[code] || code,
  );

  return (
    <DashboardWidget
      title="Публикация в каталоге"
      hint="Календарь, gate и включение публичной карточки"
      accent="venue"
      isEmpty={!loading && !profile}
      empty="Сначала создайте площадку."
    >
      {loading ? <p className="timeline">Проверяем готовность…</p> : null}
      {profile ? (
        <>
          <ul className="timeline" data-testid="venue-publication-status">
            <li>
              {profile.publication_enabled ? "● Публичная карточка включена" : "○ Публичная карточка выключена"}
            </li>
            <li>
              {profile.publication_eligible
                ? "● Серверный gate пройден"
                : "○ Есть незакрытые условия публикации"}
            </li>
            {publicHref ? (
              <li>
                <Link href={publicHref}>Открыть публичный профиль →</Link>
              </li>
            ) : null}
          </ul>
          {!profile.publication_eligible && reasons.length ? (
            <ul className="timeline">
              {reasons.map((label) => (
                <li key={label}>○ {label}</li>
              ))}
            </ul>
          ) : null}

          {canManage ? (
            <>
              <form
                className="cabinet-inline-form"
                style={{ marginTop: 12 }}
                onSubmit={(e) => void onEvidence(e)}
                data-testid="venue-publication-evidence-form"
              >
                <strong>Подтверждение календаря</strong>
                <label>
                  Календарь, дней вперёд
                  <input name="calendar_days" type="number" min={30} defaultValue={90} required />
                </label>
                <button type="submit" disabled={busy}>
                  {busy ? "Сохраняем…" : "Сохранить доказательства"}
                </button>
              </form>

              <div className="cabinet-hero-actions" style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || (!profile.publication_eligible && !profile.publication_enabled)}
                  data-testid="venue-publication-toggle"
                  onClick={() =>
                    void setPublicationEnabled(!profile.publication_enabled).then((ok) => {
                      if (ok) onChanged?.();
                    })
                  }
                >
                  {profile.publication_enabled ? "Снять с публикации" : "Опубликовать в каталоге"}
                </button>
              </div>
            </>
          ) : null}
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        </>
      ) : null}
    </DashboardWidget>
  );
}
