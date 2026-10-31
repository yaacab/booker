"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import type { PerformerArtistProfile } from "./types";

export function usePerformerProfile(orgId: string, role: string) {
  const [artistId, setArtistId] = useState("");
  const [profile, setProfile] = useState<PerformerArtistProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [tariffBusy, setTariffBusy] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const targets = await api<{ items: { resource_type: string; resource_id: string; label: string }[] }>(
        `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
      );
      const artist = targets.items.find((t) => t.resource_type === "artist");
      if (!artist) {
        setArtistId("");
        setProfile(null);
        setError("");
        return;
      }
      setArtistId(artist.resource_id);
      const page = await api<PerformerArtistProfile>(`/artists/${encodeURIComponent(artist.resource_id)}`);
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

  return {
    artistId,
    profile,
    loading,
    tariffBusy,
    updateTariff,
    deleteTariff,
    error,
    canManage: isWriteRole(role),
    publicHref: artistId ? `/artists/${artistId}` : null,
    reload,
    addTariff,
  };
}
