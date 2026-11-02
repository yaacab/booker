"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import type { PerformerArtistProfile, PerformerCalendarTarget } from "./types";

const selectedArtistKey = (orgId: string) => `booker.performer.selectedArtist.${orgId}`;

export function usePerformerProfile(orgId: string, role: string) {
  const [artistId, setArtistId] = useState("");
  const [artistTargets, setArtistTargets] = useState<PerformerCalendarTarget[]>([]);
  const [profile, setProfile] = useState<PerformerArtistProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [tariffBusy, setTariffBusy] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const targets = await api<{ items: PerformerCalendarTarget[] }>(
        `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
      );
      const artists = targets.items.filter((t) => t.resource_type === "artist");
      setArtistTargets(artists);
      if (!artists.length) {
        setArtistId("");
        setProfile(null);
        setError("");
        return;
      }
      const stored =
        typeof window !== "undefined" ? window.localStorage.getItem(selectedArtistKey(orgId)) : null;
      const selected = artists.find((item) => item.resource_id === stored) || artists[0];
      setArtistId(selected.resource_id);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(selectedArtistKey(orgId), selected.resource_id);
      }
      const page = await api<PerformerArtistProfile>(
        `/artists/${encodeURIComponent(selected.resource_id)}`,
      );
      setProfile(page);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить витрину");
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  function selectArtist(nextId: string) {
    if (!nextId || nextId === artistId) return;
    setArtistId(nextId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(selectedArtistKey(orgId), nextId);
    }
    void (async () => {
      setLoading(true);
      try {
        const page = await api<PerformerArtistProfile>(`/artists/${encodeURIComponent(nextId)}`);
        setProfile(page);
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Не удалось загрузить витрину");
        setProfile(null);
      } finally {
        setLoading(false);
      }
    })();
  }

  async function addTariff(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!artistId || !isWriteRole(role)) return;
    const form = e.currentTarget;
    const data = new FormData(form);
    const title = String(data.get("title") || "").trim();
    const honorarium = Number(data.get("honorarium") || 0);
    if (!title || honorarium <= 0) {
      setError("Укажите название тарифа и гонорар");
      return;
    }
    setTariffBusy(true);
    setError("");
    try {
      await api(`/artists/${encodeURIComponent(artistId)}/tariffs`, {
        method: "POST",
        body: JSON.stringify({ title, honorarium_rub: honorarium, hours: 2 }),
      });
      trackClientEvent("cabinet.tariff_added", { artist_id: artistId });
      form.reset();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить тариф");
    } finally {
      setTariffBusy(false);
    }
  }

  async function updateTariff(id: string, patch: { title?: string; honorarium_rub?: number }) {
    if (!artistId || !isWriteRole(role)) return false;
    if (patch.title !== undefined && !patch.title.trim()) { setError("Название тарифа не может быть пустым"); return false; }
    if (patch.honorarium_rub !== undefined && !(patch.honorarium_rub > 0)) { setError("Гонорар должен быть больше нуля"); return false; }
    setTariffBusy(true);
    setError("");
    try {
      await api(`/artists/${encodeURIComponent(artistId)}/tariffs/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить тариф");
      return false;
    } finally {
      setTariffBusy(false);
    }
  }

  async function deleteTariff(id: string) {
    if (!artistId || !isWriteRole(role)) return;
    setTariffBusy(true);
    setError("");
    try {
      await api(`/artists/${encodeURIComponent(artistId)}/tariffs/${encodeURIComponent(id)}`, { method: "DELETE" });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить тариф");
    } finally {
      setTariffBusy(false);
    }
  }

  async function updateRider(fields: { format?: string; lineup?: string; tech?: string; travel?: string }) {
    if (!artistId || !isWriteRole(role) || !profile) return false;
    setTariffBusy(true);
    setError("");
    try {
      const rider = {
        ...profile.rider,
        ...Object.fromEntries(
          Object.entries(fields)
            .map(([key, value]) => [key, String(value || "").trim()])
            .filter(([, value]) => Boolean(value)),
        ),
      };
      await api(`/artists/${encodeURIComponent(artistId)}`, {
        method: "PATCH",
        body: JSON.stringify({ rider_json: JSON.stringify(rider) }),
      });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить райдер");
      return false;
    } finally {
      setTariffBusy(false);
    }
  }

  async function savePublicationEvidence(input: {
    media_url: string;
    media_source_url: string;
    media_rights_status: "owned" | "licensed" | "official_permission";
    calendar_days: number;
  }) {
    if (!artistId || !isWriteRole(role)) return false;
    setTariffBusy(true);
    setError("");
    try {
      const through = new Date(Date.now() + Math.max(30, input.calendar_days) * 86_400_000).toISOString();
      await api(`/artists/${encodeURIComponent(artistId)}/publication-evidence`, {
        method: "PUT",
        body: JSON.stringify({
          media_url: input.media_url.trim(),
          media_source_url: input.media_source_url.trim() || input.media_url.trim(),
          media_rights_status: input.media_rights_status,
          rights_attested: true,
          calendar_confirmed_through: through,
        }),
      });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить доказательства публикации");
      return false;
    } finally {
      setTariffBusy(false);
    }
  }

  async function setPublicationEnabled(enabled: boolean) {
    if (!artistId || !isWriteRole(role) || !profile) return false;
    setTariffBusy(true);
    setError("");
    try {
      await api(`/artists/${encodeURIComponent(artistId)}/publication`, {
        method: "PUT",
        body: JSON.stringify({
          enabled,
          state_version: profile.publication_state_version ?? 0,
        }),
      });
      trackClientEvent(enabled ? "cabinet.publication_enabled" : "cabinet.publication_disabled", {
        artist_id: artistId,
      });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить публикацию");
      return false;
    } finally {
      setTariffBusy(false);
    }
  }

  async function requestVerification() {
    if (!artistId || !isWriteRole(role) || !profile) return false;
    setTariffBusy(true);
    setError("");
    try {
      await api(`/artists/${encodeURIComponent(artistId)}/verification-request`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      trackClientEvent("cabinet.verification_requested", { artist_id: artistId });
      await reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить запрос на проверку");
      return false;
    } finally {
      setTariffBusy(false);
    }
  }

  return {
    artistId,
    artistTargets,
    selectArtist,
    profile,
    loading,
    tariffBusy,
    updateTariff,
    deleteTariff,
    updateRider,
    savePublicationEvidence,
    setPublicationEnabled,
    requestVerification,
    error,
    canManage: isWriteRole(role),
    publicHref: artistId ? `/artists/${artistId}` : null,
    reload,
    addTariff,
  };
}
