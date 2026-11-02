"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import type { PerformerCalendarTarget, PerformerService } from "./types";

type ServiceTemplate = { id: string; title: string; category_code: string };

export function usePerformerServices(orgId: string, role: string) {
  const [services, setServices] = useState<PerformerService[]>([]);
  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [targets, setTargets] = useState<PerformerCalendarTarget[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const [svc, tpl, calendarTargets] = await Promise.all([
        api<{ items: PerformerService[] }>(`/services?organization_id=${encodeURIComponent(orgId)}`),
        api<{ items: ServiceTemplate[] }>("/service-templates").catch(() => ({ items: [] })),
        api<{ items: PerformerCalendarTarget[] }>(
          `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
        ).catch(() => ({ items: [] })),
      ]);
      setServices(svc.items);
      setTemplates(tpl.items);
      setTargets(calendarTargets.items.filter((item) => item.resource_type === "artist"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить услуги");
      setServices([]);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function createService(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!orgId || !isWriteRole(role)) return;
    const form = e.currentTarget;
    const data = new FormData(form);
    const title = String(data.get("title") || "").trim();
    if (!title) {
      setError("Укажите название");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const category = String(data.get("category") || "dj");
      const body: Record<string, unknown> = {
        organization_id: orgId,
        category_code: category,
        title,
        description: String(data.get("description") || "").trim(),
        published: data.get("published") === "on",
      };
      const honorarium = String(data.get("honorarium") || "").trim();
      if (honorarium) body.honorarium_rub = Number(honorarium);
      const resourceId = String(data.get("resource_id") || "").trim();
      if (resourceId) {
        body.resource_type = "artist";
        body.resource_id = resourceId;
      }
      const created = await api<PerformerService>("/services", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (data.get("sync_tariff") === "on" && created.resource_id && created.honorarium_rub) {
        await api(`/services/${encodeURIComponent(created.id)}/sync-tariff`, { method: "POST" });
      }
      setServices((prev) => [...prev, created]);
      trackClientEvent("cabinet.service_created", { category });
      form.reset();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать услугу");
    } finally {
      setBusy(false);
    }
  }

  async function createFromTemplate(templateId: string) {
    if (!orgId || !isWriteRole(role)) return;
    setTemplateBusy(templateId);
    setError("");
    try {
      const created = await api<PerformerService>("/services/from-template", {
        method: "POST",
        body: JSON.stringify({ organization_id: orgId, template_id: templateId }),
      });
      setServices((prev) => [...prev, created]);
      trackClientEvent("cabinet.service_created", { from_template: templateId });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать из шаблона");
    } finally {
      setTemplateBusy(null);
    }
  }

  async function patchService(id: string, patch: Partial<PerformerService>) {
    if (!orgId || !isWriteRole(role)) return false;
    setBusy(true);
    setError("");
    try {
      const updated = await api<PerformerService>(`/services/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setServices((prev) => prev.map((item) => (item.id === id ? updated : item)));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить услугу");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function deleteService(id: string) {
    if (!orgId || !isWriteRole(role)) return;
    setBusy(true);
    setError("");
    try {
      await api(`/services/${encodeURIComponent(id)}`, { method: "DELETE" });
      setServices((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить услугу");
    } finally {
      setBusy(false);
    }
  }

  async function bindService(id: string, resourceId: string) {
    if (!orgId || !isWriteRole(role) || !resourceId) return false;
    setBusy(true);
    setError("");
    try {
      const updated = await api<PerformerService>(`/services/${encodeURIComponent(id)}/profile`, {
        method: "PUT",
        body: JSON.stringify({ resource_type: "artist", resource_id: resourceId }),
      });
      setServices((prev) => prev.map((item) => (item.id === id ? updated : item)));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось привязать профиль");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function syncTariff(id: string) {
    if (!orgId || !isWriteRole(role)) return false;
    setBusy(true);
    setError("");
    try {
      await api(`/services/${encodeURIComponent(id)}/sync-tariff`, { method: "POST" });
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать тариф каталога");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return {
    services,
    templates,
    targets,
    loading,
    busy,
    templateBusy,
    error,
    canManage: isWriteRole(role),
    reload,
    createService,
    createFromTemplate,
    patchService,
    deleteService,
    bindService,
    syncTariff,
  };
}
