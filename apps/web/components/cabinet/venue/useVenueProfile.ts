"use client";

import { useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import type { VenueProfile } from "./types";

export function useVenueProfile(venueId: string, role: string) {
  const [profile, setProfile] = useState<VenueProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!venueId) {
      setProfile(null);
      return;
    }
    setLoading(true);
    try {
      const page = await api<VenueProfile>(`/venues/${encodeURIComponent(venueId)}`);
      setProfile(page);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить площадку");
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [venueId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function saveCalendarEvidence(calendarDays: number) {
    if (!venueId || !isWriteRole(role)) return false;
    setBusy(true);
    setError("");
    try {
      const through = new Date(Date.now() + Math.max(30, calendarDays) * 86_400_000).toISOString();
      await api(`/venues/${encodeURIComponent(venueId)}/publication-evidence`, {
        method: "PUT",
        body: JSON.stringify({ calendar_confirmed_through: through }),
      });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить календарь");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function savePhoto(input: {
    photo_url: string;
    photo_source_url: string;
    photo_rights_status: "owned" | "licensed" | "official_permission";
  }) {
    if (!venueId || !isWriteRole(role)) return false;
    setBusy(true);
    setError("");
    try {
      await api(`/venues/${encodeURIComponent(venueId)}/photos`, {
        method: "PUT",
        body: JSON.stringify({
          photo_url: input.photo_url.trim(),
          photo_source_url: input.photo_source_url.trim() || input.photo_url.trim(),
          photo_rights_status: input.photo_rights_status,
          rights_attested: true,
          sort_order: 0,
        }),
      });
      trackClientEvent("cabinet.venue_photo_saved", { venue_id: venueId });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить фото");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function setPublicationEnabled(enabled: boolean) {
    if (!venueId || !isWriteRole(role) || !profile) return false;
    setBusy(true);
    setError("");
    try {
      await api(`/venues/${encodeURIComponent(venueId)}/publication`, {
        method: "PUT",
        body: JSON.stringify({
          enabled,
          state_version: profile.publication_state_version ?? 0,
        }),
      });
      trackClientEvent(enabled ? "cabinet.venue_publication_enabled" : "cabinet.venue_publication_disabled", {
        venue_id: venueId,
      });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить публикацию");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return {
    profile,
    loading,
    busy,
    error,
    canManage: isWriteRole(role),
    publicHref: venueId ? `/venues/${venueId}` : null,
    reload,
    saveCalendarEvidence,
    savePhoto,
    setPublicationEnabled,
  };
}
