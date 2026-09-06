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
    loading,
    busy,
    templateBusy,
    error,
    canManage,
    createService,
    createFromTemplate,
  } = usePerformerServices(orgId, role);

  return (
    <DashboardWidget
      title="Услуги"
      hint="Прайс в каталоге — заказчик видит ориентир, счёт только в Deal Room"
      accent="performer"
      isEmpty={!loading && services.length === 0}
      empty="Добавьте услугу или выберите шаблон — без прайса вас реже находят в поиске."
    >
      {loading ? <p className="timeline">Загружаем услуги…</p> : null}
      {services.length > 0 ? (
        <ul className="dashboard-list" data-testid="performer-services-list">
          {services.map((s) => (
            <li key={s.id}>
              <article className="dashboard-action-card">
                <strong>{s.title}</strong>
                <span className="chip live">{categoryLabel(s.category_code)}</span>
                {s.honorarium_rub != null ? <span className="mono">{money(s.honorarium_rub)}</span> : null}
                {s.description ? <p className="timeline">{s.description}</p> : null}
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
          <label>
            Описание
            <textarea name="description" rows={2} />
          </label>
          <label>
            Гонорар, ₽ <span className="timeline">(необязательно)</span>
            <input name="honorarium" type="number" min={0} />
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
