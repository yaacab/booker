"use client";

import { FormEvent } from "react";
import { DashboardWidget } from "../../DashboardWidget";
import { usePerformerProfile } from "../usePerformerProfile";

const REASON_LABELS: Record<string, string> = {
  publication_enabled: "Публичная карточка выключена",
  verified: "Нужна верификация администратором",
  tariff: "Добавьте тариф с ценой",
  media: "Подтвердите медиа и права",
  representative: "Нужен представитель owner/admin",
  calendar_30d: "Подтвердите календарь минимум на 30 дней",
  calendar_entries: "Добавьте актуальные записи в календарь",
};

type Props = { orgId: string; role: string; onChanged?: () => void };

export function PublicationWidget({ orgId, role, onChanged }: Props) {
  const {
    profile,
    artistTargets,
    selectArtist,
    loading,
    error,
    canManage,
    tariffBusy,
    savePublicationEvidence,
    setPublicationEnabled,
  } = usePerformerProfile(orgId, role);

  async function onEvidence(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const ok = await savePublicationEvidence({
      media_url: String(data.get("media_url") || ""),
      media_source_url: String(data.get("media_source_url") || ""),
      media_rights_status: String(data.get("media_rights_status") || "owned") as
        | "owned"
        | "licensed"
        | "official_permission",
      calendar_days: Number(data.get("calendar_days") || 90),
    });
    if (ok) onChanged?.();
  }

  const reasons = (profile?.publication_reason_codes || []).map(
    (code) => REASON_LABELS[code] || code,
  );

  return (
    <DashboardWidget
      title="Публикация в каталоге"
      hint="Доказательства и включение публичной карточки"
      accent="performer"
      isEmpty={!loading && !profile}
      empty="Сначала создайте профиль артиста."
    >
      {loading ? <p className="timeline">Проверяем готовность…</p> : null}
      {profile ? (
        <>
          {artistTargets.length > 1 ? (
            <label className="cabinet-inline-form">
              Профиль
              <select value={profile.id} onChange={(e) => selectArtist(e.target.value)}>
                {artistTargets.map((item) => (
                  <option key={item.resource_id} value={item.resource_id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <ul className="timeline" data-testid="performer-publication-status">
            <li>
              {profile.publication_enabled ? "● Публичная карточка включена" : "○ Публичная карточка выключена"}
            </li>
            <li>
              {profile.publication_eligible
                ? "● Серверный gate пройден"
                : "○ Есть незакрытые условия публикации"}
            </li>
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
                data-testid="performer-publication-evidence-form"
              >
                <strong>Доказательства публикации</strong>
                <label>
                  Медиа URL
                  <input
                    name="media_url"
                    defaultValue={profile.media_url || "/design/puzzle-dj.png"}
                    required
                    placeholder="https://… или /design/…"
                  />
                </label>
                <label>
                  Источник медиа
                  <input
                    name="media_source_url"
                    defaultValue={profile.media_url || "/design/puzzle-dj.png"}
                    required
                  />
                </label>
                <label>
                  Права
                  <select name="media_rights_status" defaultValue="owned">
                    <option value="owned">Собственные</option>
                    <option value="licensed">Лицензия</option>
                    <option value="official_permission">Официальное разрешение</option>
                  </select>
                </label>
                <label>
                  Календарь, дней вперёд
                  <input name="calendar_days" type="number" min={30} defaultValue={90} required />
                </label>
                <button type="submit" disabled={tariffBusy}>
                  {tariffBusy ? "Сохраняем…" : "Сохранить доказательства"}
                </button>
              </form>

              <div className="cabinet-hero-actions" style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={tariffBusy || (!profile.publication_eligible && !profile.publication_enabled)}
                  data-testid="performer-publication-toggle"
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
