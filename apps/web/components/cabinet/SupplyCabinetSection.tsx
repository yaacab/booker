"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, isWriteRole, trackClientEvent } from "@/lib/api";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { formatWhen, money } from "@/lib/format";

type ServiceItem = {
  id: string;
  title: string;
  category_code: string;
  description: string;
  honorarium_rub: number | null;
};

const SERVICE_CATEGORIES = Object.keys(CATEGORY);

type SupplyCabinetSectionProps = {
  orgId: string;
  role: string;
  onCompletenessChange?: (score: number) => void;
};

export function SupplyCabinetSection({ orgId, role, onCompletenessChange }: SupplyCabinetSectionProps) {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [serviceTitle, setServiceTitle] = useState("");
  const [serviceCategory, setServiceCategory] = useState("dj");
  const [serviceDescription, setServiceDescription] = useState("");
  const [serviceHonorarium, setServiceHonorarium] = useState("");
  const [serviceBusy, setServiceBusy] = useState(false);
  const [serviceError, setServiceError] = useState("");
  const [templates, setTemplates] = useState<{ id: string; title: string; category_code: string }[]>([]);
  const [templateBusy, setTemplateBusy] = useState<string | null>(null);
  const [calendarTargets, setCalendarTargets] = useState<
    { resource_type: string; resource_id: string; label: string }[]
  >([]);
  const [calendarTargetId, setCalendarTargetId] = useState("");
  const [icalUrl, setIcalUrl] = useState("");
  const [icalBusy, setIcalBusy] = useState(false);
  const [icalResult, setIcalResult] = useState("");
  const [icalError, setIcalError] = useState("");
  const [vacationItems, setVacationItems] = useState<
    {
      resource_type: string;
      resource_id: string;
      label: string;
      active: boolean;
      starts_at: string | null;
      ends_at: string | null;
    }[]
  >([]);
  const [vacationTargetId, setVacationTargetId] = useState("");
  const [vacationStart, setVacationStart] = useState("");
  const [vacationEnd, setVacationEnd] = useState("");
  const [vacationBusy, setVacationBusy] = useState(false);
  const [vacationError, setVacationError] = useState("");
  const [vacationResult, setVacationResult] = useState("");

  useEffect(() => {
    if (!orgId) return;
    void Promise.all([
      api<{ items: ServiceItem[] }>(`/services?organization_id=${encodeURIComponent(orgId)}`).then((res) =>
        setServices(res.items),
      ),
      api<{ items: { resource_type: string; resource_id: string; label: string }[] }>(
        `/organizations/${encodeURIComponent(orgId)}/calendar-targets`,
      ).then((res) => {
        setCalendarTargets(res.items);
        if (res.items[0]) {
          setCalendarTargetId(res.items[0].resource_id);
          setVacationTargetId(res.items[0].resource_id);
        }
      }),
      api<{
        items: {
          resource_type: string;
          resource_id: string;
          label: string;
          active: boolean;
          starts_at: string | null;
          ends_at: string | null;
        }[];
      }>(`/organizations/${encodeURIComponent(orgId)}/vacation`).then((res) => setVacationItems(res.items)),
    ]).catch(() => {
      setServices([]);
      setCalendarTargets([]);
      setVacationItems([]);
    });
    void api<{ items: { id: string; title: string; category_code: string }[] }>("/service-templates")
      .then((res) => setTemplates(res.items))
      .catch(() => setTemplates([]));
  }, [orgId]);

  const canManage = isWriteRole(role);
  const activeVacation = vacationItems.find((v) => v.resource_id === vacationTargetId && v.active);

  async function createService(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!orgId || !canManage) return;
    const title = serviceTitle.trim();
    if (!title) {
      setServiceError("Укажите название");
      return;
    }
    setServiceBusy(true);
    setServiceError("");
    try {
      const body: Record<string, unknown> = {
        organization_id: orgId,
        category_code: serviceCategory,
        title,
        description: serviceDescription.trim(),
      };
      const honorarium = serviceHonorarium.trim();
      if (honorarium) body.honorarium_rub = Number(honorarium);
      const created = await api<ServiceItem>("/services", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setServices((prev) => [...prev, created]);
      trackClientEvent("cabinet.service_created", { category: serviceCategory });
      setServiceTitle("");
      setServiceDescription("");
      setServiceHonorarium("");
    } catch (err) {
      setServiceError(err instanceof Error ? err.message : "Не удалось создать услугу");
    } finally {
      setServiceBusy(false);
    }
  }

  async function createFromTemplate(templateId: string) {
    if (!orgId || !canManage) return;
    setTemplateBusy(templateId);
    setServiceError("");
    try {
      const created = await api<ServiceItem>("/services/from-template", {
        method: "POST",
        body: JSON.stringify({ organization_id: orgId, template_id: templateId }),
      });
      setServices((prev) => [...prev, created]);
      trackClientEvent("cabinet.service_created", { from_template: templateId });
    } catch (err) {
      setServiceError(err instanceof Error ? err.message : "Не удалось создать из шаблона");
    } finally {
      setTemplateBusy(null);
    }
  }

  async function importIcal(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!orgId || !canManage) return;
    const target = calendarTargets.find((t) => t.resource_id === calendarTargetId);
    if (!target) {
      setIcalError("Выберите календарь");
      return;
    }
    const url = icalUrl.trim();
    if (!url) {
      setIcalError("Укажите ссылку iCal");
      return;
    }
    setIcalBusy(true);
    setIcalError("");
    setIcalResult("");
    try {
      const res = await api<{ imported: number; skipped: number; removed_open: number }>(
        "/calendar/ical/import",
        {
          method: "POST",
          body: JSON.stringify({
            organization_id: orgId,
            resource_type: target.resource_type,
            resource_id: target.resource_id,
            ical_url: url,
          }),
        },
      );
      setIcalResult(
        `Импортировано занятостей: ${res.imported}, пропущено: ${res.skipped}, закрыто открытых слотов: ${res.removed_open}`,
      );
      trackClientEvent("cabinet.ical_imported", { imported: res.imported });
      const refreshed = await api<{ score: number }>(
        `/organizations/${encodeURIComponent(orgId)}/supply-completeness`,
      );
      onCompletenessChange?.(refreshed.score);
    } catch (err) {
      setIcalError(err instanceof Error ? err.message : "Не удалось импортировать iCal");
    } finally {
      setIcalBusy(false);
    }
  }

  async function setVacation(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!orgId || !canManage) return;
    const target = calendarTargets.find((t) => t.resource_id === vacationTargetId);
    if (!target) {
      setVacationError("Выберите календарь");
      return;
    }
    if (!vacationStart || !vacationEnd) {
      setVacationError("Укажите даты отпуска");
      return;
    }
    setVacationBusy(true);
    setVacationError("");
    setVacationResult("");
    try {
      const res = await api<{ removed_open: number }>("/calendar/vacation", {
        method: "POST",
        body: JSON.stringify({
          organization_id: orgId,
          resource_type: target.resource_type,
          resource_id: target.resource_id,
          starts_at: new Date(vacationStart).toISOString(),
          ends_at: new Date(vacationEnd).toISOString(),
        }),
      });
      setVacationResult(
        `Отпуск включён. Закрыто открытых слотов: ${res.removed_open}. В этот период вас не увидят в каталоге.`,
      );
      trackClientEvent("cabinet.vacation_set");
      const refreshed = await api<{
        items: {
          resource_type: string;
          resource_id: string;
          label: string;
          active: boolean;
          starts_at: string | null;
          ends_at: string | null;
        }[];
      }>(`/organizations/${encodeURIComponent(orgId)}/vacation`);
      setVacationItems(refreshed.items);
    } catch (err) {
      setVacationError(err instanceof Error ? err.message : "Не удалось включить отпуск");
    } finally {
      setVacationBusy(false);
    }
  }

  async function clearVacation() {
    if (!orgId || !canManage) return;
    const target = calendarTargets.find((t) => t.resource_id === vacationTargetId);
    if (!target) return;
    setVacationBusy(true);
    setVacationError("");
    setVacationResult("");
    try {
      await api("/calendar/vacation", {
        method: "DELETE",
        body: JSON.stringify({
          organization_id: orgId,
          resource_type: target.resource_type,
          resource_id: target.resource_id,
        }),
      });
      setVacationResult("Отпуск снят.");
      setVacationStart("");
      setVacationEnd("");
      const refreshed = await api<{
        items: {
          resource_type: string;
          resource_id: string;
          label: string;
          active: boolean;
          starts_at: string | null;
          ends_at: string | null;
        }[];
      }>(`/organizations/${encodeURIComponent(orgId)}/vacation`);
      setVacationItems(refreshed.items);
    } catch (err) {
      setVacationError(err instanceof Error ? err.message : "Не удалось снять отпуск");
    } finally {
      setVacationBusy(false);
    }
  }

  if (!orgId) return null;

  return (
    <section className="supply-section" style={{ marginTop: 28 }} aria-labelledby="cabinet-supply-heading">
      <h2 id="cabinet-supply-heading">Услуги и занятость</h2>
      <p className="timeline">Прайс в каталоге, импорт занятости из календаря и отпуск. Свободные слоты открываются блоком выше.</p>
      {services.length > 0 ? (
        <ul>
          {services.map((s) => (
            <li key={s.id}>
              <strong>{s.title}</strong> · {categoryLabel(s.category_code)}
              {s.honorarium_rub != null ? ` · ${money(s.honorarium_rub)}` : ""}
              {s.description ? <span className="timeline"> — {s.description}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="timeline">Пока нет услуг в каталоге организации.</p>
      )}
      {canManage && templates.length > 0 ? (
        <div className="card" style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="timeline">Из шаблона:</span>
          {templates.map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              disabled={templateBusy === tpl.id}
              onClick={() => void createFromTemplate(tpl.id)}
            >
              {templateBusy === tpl.id ? "…" : tpl.title}
            </button>
          ))}
        </div>
      ) : null}
      {canManage ? (
        <form className="card" style={{ display: "grid", gap: 12, maxWidth: 420, marginTop: 12 }} onSubmit={createService}>
          <label>
            Название
            <input value={serviceTitle} onChange={(e) => setServiceTitle(e.target.value)} required />
          </label>
          <label>
            Категория
            <select value={serviceCategory} onChange={(e) => setServiceCategory(e.target.value)}>
              {SERVICE_CATEGORIES.map((code) => (
                <option key={code} value={code}>
                  {CATEGORY[code]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Описание
            <textarea value={serviceDescription} onChange={(e) => setServiceDescription(e.target.value)} rows={3} />
          </label>
          <label>
            Гонорар, ₽ <span className="timeline">(необязательно)</span>
            <input
              type="number"
              min={0}
              value={serviceHonorarium}
              onChange={(e) => setServiceHonorarium(e.target.value)}
            />
          </label>
          {serviceError ? <p style={{ color: "var(--danger)" }}>{serviceError}</p> : null}
          <button type="submit" disabled={serviceBusy}>
            {serviceBusy ? "Сохраняем…" : "Добавить услугу"}
          </button>
        </form>
      ) : (
        <p className="timeline">Только просмотр: услуги добавляет менеджер.</p>
      )}
      {canManage && calendarTargets.length > 0 ? (
        <form
          className="card"
          style={{ display: "grid", gap: 12, maxWidth: 480, marginTop: 12 }}
          onSubmit={importIcal}
        >
          <strong>Занятость из iCal</strong>
          <p className="timeline">
            Импорт busy-событий из Google Calendar или другого iCal-фида. Пересекающиеся открытые слоты будут закрыты.
          </p>
          {calendarTargets.length > 1 ? (
            <label>
              Календарь
              <select value={calendarTargetId} onChange={(e) => setCalendarTargetId(e.target.value)}>
                {calendarTargets.map((t) => (
                  <option key={t.resource_id} value={t.resource_id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label>
            Ссылка iCal
            <input
              type="url"
              value={icalUrl}
              onChange={(e) => setIcalUrl(e.target.value)}
              placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
              required
            />
          </label>
          {icalError ? <p style={{ color: "var(--danger)" }}>{icalError}</p> : null}
          {icalResult ? <p className="timeline">{icalResult}</p> : null}
          <button type="submit" disabled={icalBusy}>
            {icalBusy ? "Импортируем…" : "Импортировать занятость"}
          </button>
        </form>
      ) : null}
      {canManage && calendarTargets.length > 0 ? (
        <form
          className="card"
          style={{ display: "grid", gap: 12, maxWidth: 480, marginTop: 12 }}
          onSubmit={setVacation}
        >
          <strong>Режим отпуска</strong>
          <p className="timeline">
            На период отпуска профиль скрывается из поиска по датам, пересекающиеся открытые слоты закрываются.
          </p>
          {activeVacation ? (
            <p className="timeline">
              Сейчас активен отпуск до {activeVacation.ends_at ? formatWhen(activeVacation.ends_at) : "—"}
            </p>
          ) : null}
          {calendarTargets.length > 1 ? (
            <label>
              Календарь
              <select value={vacationTargetId} onChange={(e) => setVacationTargetId(e.target.value)}>
                {calendarTargets.map((t) => (
                  <option key={t.resource_id} value={t.resource_id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label>
            Начало
            <input
              type="datetime-local"
              value={vacationStart}
              onChange={(e) => setVacationStart(e.target.value)}
              required
            />
          </label>
          <label>
            Окончание
            <input
              type="datetime-local"
              value={vacationEnd}
              onChange={(e) => setVacationEnd(e.target.value)}
              required
            />
          </label>
          {vacationError ? <p style={{ color: "var(--danger)" }}>{vacationError}</p> : null}
          {vacationResult ? <p className="timeline">{vacationResult}</p> : null}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="submit" disabled={vacationBusy}>
              {vacationBusy ? "Сохраняем…" : activeVacation ? "Обновить отпуск" : "Включить отпуск"}
            </button>
            {activeVacation ? (
              <button type="button" className="secondary" disabled={vacationBusy} onClick={() => void clearVacation()}>
                Снять отпуск
              </button>
            ) : null}
          </div>
        </form>
      ) : null}
    </section>
  );
}
