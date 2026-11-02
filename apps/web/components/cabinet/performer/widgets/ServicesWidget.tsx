"use client";

import Link from "next/link";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import { usePerformerServices } from "../usePerformerServices";

const SERVICE_CATEGORIES = Object.keys(CATEGORY);

type ServicesWidgetProps = {
  orgId: string;
  role: string;
  compact?: boolean;
};

export function ServicesWidget({ orgId, role, compact = false }: ServicesWidgetProps) {
  const {
    services,
    templates,
    targets,
    loading,
    busy,
    templateBusy,
    error,
    canManage,
    createService,
    createFromTemplate,
    patchService,
    deleteService,
    bindService,
    syncTariff,
  } = usePerformerServices(orgId, role);

  return (
    <DashboardWidget
      title="Услуги"
      hint="Форматы выступлений. Для каталога нужен ещё тариф на профиле."
      accent="performer"
      span={compact ? "half" : "full"}
    >
      {loading ? <p className="timeline">Загружаем услуги…</p> : null}
      {!loading && services.length === 0 ? (
        <p className="dashboard-empty timeline">Добавьте первую услугу или выберите готовый шаблон.</p>
      ) : null}
      {services.length > 0 ? (
        <ul className="dashboard-list workspace-service-list" data-testid="performer-services-list">
          {services.map((s) => (
            <li key={s.id}>
              <article className="dashboard-action-card">
                <strong>{s.title}</strong>
                <span className="chip live">{categoryLabel(s.category_code)}</span>
                {s.honorarium_rub != null ? <span className="mono">{money(s.honorarium_rub)}</span> : null}
                <span className="chip">{s.published ? "в витрине услуг" : "скрыта"}</span>
                {s.resource_id ? (
                  <span className="timeline">привязана к профилю</span>
                ) : (
                  <span className="timeline">без профиля — не попадёт в public</span>
                )}
                {s.description ? <p className="timeline">{s.description}</p> : null}
                {canManage && !compact ? (
                  <div className="cabinet-hero-actions" style={{ marginTop: 8 }}>
                    <button
                      type="button"
                      className="linkish"
                      disabled={busy}
                      onClick={() => void patchService(s.id, { published: !s.published })}
                    >
                      {s.published ? "Скрыть" : "Показать"}
                    </button>
                    {s.resource_id && s.honorarium_rub ? (
                      <button
                        type="button"
                        className="linkish"
                        disabled={busy}
                        onClick={() => void syncTariff(s.id)}
                      >
                        В тариф каталога
                      </button>
                    ) : null}
                    {!s.resource_id && targets.length === 1 ? (
                      <button
                        type="button"
                        className="linkish"
                        disabled={busy}
                        onClick={() => void bindService(s.id, targets[0].resource_id)}
                      >
                        Привязать профиль
                      </button>
                    ) : null}
                    {!s.resource_id && targets.length > 1 ? (
                      <label>
                        Профиль
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) void bindService(s.id, e.target.value);
                          }}
                        >
                          <option value="">Выбрать…</option>
                          {targets.map((t) => (
                            <option key={t.resource_id} value={t.resource_id}>
                              {t.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <button
                      type="button"
                      className="linkish"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(`Удалить услугу «${s.title}»?`)) void deleteService(s.id);
                      }}
                    >
                      Удалить
                    </button>
                  </div>
                ) : null}
              </article>
            </li>
          ))}
        </ul>
      ) : null}

      {!compact && canManage && templates.length > 0 ? (
        <div className="cabinet-inline-form" style={{ marginTop: 12 }}>
          <p className="timeline">Из шаблона:</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
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
        </div>
      ) : null}

      {canManage && !compact ? (
        <form
          className="cabinet-inline-form"
          style={{ marginTop: 12 }}
          onSubmit={(e) => void createService(e)}
          data-testid="performer-service-form"
          id="performer-service-form"
        >
          <label>
            Название
            <input name="title" required />
          </label>
          <label>
            Категория
            <select name="category" defaultValue="dj">
              {SERVICE_CATEGORIES.map((code) => (
                <option key={code} value={code}>
                  {CATEGORY[code]}
                </option>
              ))}
            </select>
          </label>
          {targets.length > 1 ? (
            <label>
              Профиль
              <select name="resource_id" defaultValue={targets[0]?.resource_id || ""}>
                {targets.map((t) => (
                  <option key={t.resource_id} value={t.resource_id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          ) : targets.length === 1 ? (
            <input type="hidden" name="resource_id" value={targets[0].resource_id} />
          ) : null}
          <label>
            Описание
            <textarea name="description" rows={2} />
          </label>
          <label>
            Гонорар, ₽ <span className="timeline">(необязательно)</span>
            <input name="honorarium" type="number" min={1} />
          </label>
          <label>
            <input name="published" type="checkbox" defaultChecked /> В витрине услуг
          </label>
          <label>
            <input name="sync_tariff" type="checkbox" defaultChecked /> Также создать тариф каталога
          </label>
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={busy}>
            {busy ? "Сохраняем…" : "Добавить услугу"}
          </button>
        </form>
      ) : null}

      {compact ? (
        <p className="timeline">
          <Link href="/cabinet/performer/services">Управление услугами →</Link>
        </p>
      ) : null}

      {!canManage && services.length > 0 ? (
        <p className="timeline">Только просмотр: услуги редактирует менеджер.</p>
      ) : null}
    </DashboardWidget>
  );
}
