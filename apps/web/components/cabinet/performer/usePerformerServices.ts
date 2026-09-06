"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import type { PerformerService } from "./types";

type ServiceTemplate = { id: string; title: string; category_code: string };

export function usePerformerServices(orgId: string, role: string) {
  const [services, setServices] = useState<PerformerService[]>([]);
  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const [svc, tpl] = await Promise.all([
        api<{ items: PerformerService[] }>(`/services?organization_id=${encodeURIComponent(orgId)}`),
        api<{ items: ServiceTemplate[] }>("/service-templates").catch(() => ({ items: [] })),
      ]);
      setServices(svc.items);
      setTemplates(tpl.items);
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
      const body: Record<string, unknown> = {
        organization_id: orgId,
        category_code: String(data.get("category") || "dj"),
        title,
        description: String(data.get("description") || "").trim(),
      };
      const honorarium = String(data.get("honorarium") || "").trim();
      if (honorarium) body.honorarium_rub = Number(honorarium);
      const created = await api<PerformerService>("/services", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setServices((prev) => [...prev, created]);
      trackClientEvent("cabinet.service_created", { category: body.category_code });
      form.reset();
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

  return {
    services,
    templates,
    loading,
    busy,
    templateBusy,
    error,
    canManage: isWriteRole(role),
    reload,
    createService,
    createFromTemplate,
  };
}
