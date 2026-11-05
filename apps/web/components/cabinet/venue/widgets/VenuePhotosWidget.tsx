"use client";

import { FormEvent } from "react";
import { DashboardWidget } from "../../DashboardWidget";
import { useVenueProfile } from "../useVenueProfile";

type Props = { venueId: string; role: string; onChanged?: () => void };

export function VenuePhotosWidget({ venueId, role, onChanged }: Props) {
  const { profile, loading, busy, error, canManage, savePhoto } = useVenueProfile(venueId, role);
  const photos = profile?.photos || [];

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const ok = await savePhoto({
      photo_url: String(data.get("photo_url") || ""),
      photo_source_url: String(data.get("photo_source_url") || ""),
      photo_rights_status: String(data.get("photo_rights_status") || "owned") as
        | "owned"
        | "licensed"
        | "official_permission",
    });
    if (ok) onChanged?.();
  }

  return (
    <DashboardWidget
      title="Фото площадки"
      hint="Публичные фото с подтверждением прав"
      accent="venue"
      isEmpty={!loading && !profile}
      empty="Сначала создайте площадку."
    >
      {loading ? <p className="timeline">Загружаем фото…</p> : null}
      {profile ? (
        <>
          <ul className="timeline" data-testid="venue-photos-list">
            {photos.length ? (
              photos.map((photo, index) => (
                <li key={photo.id || photo.url || photo.photo_url || index}>
                  ● {photo.url || photo.photo_url}
                  {photo.rights_status ? ` · ${photo.rights_status}` : ""}
                </li>
              ))
            ) : (
              <li>○ Фото ещё не добавлены</li>
            )}
          </ul>
          {canManage ? (
            <form
              className="cabinet-inline-form"
              style={{ marginTop: 12 }}
              onSubmit={(e) => void onSubmit(e)}
              data-testid="venue-photos-form"
            >
              <strong>Добавить / обновить фото</strong>
              <label>
                URL фото
                <input name="photo_url" defaultValue="/design/puzzle-venue.png" required />
              </label>
              <label>
                Источник
                <input name="photo_source_url" defaultValue="/design/puzzle-venue.png" required />
              </label>
              <label>
                Права
                <select name="photo_rights_status" defaultValue="owned">
                  <option value="owned">Собственные</option>
                  <option value="licensed">Лицензия</option>
                  <option value="official_permission">Официальное разрешение</option>
                </select>
              </label>
              <button type="submit" disabled={busy}>
                {busy ? "Сохраняем…" : "Сохранить фото"}
              </button>
            </form>
          ) : null}
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        </>
      ) : null}
    </DashboardWidget>
  );
}
