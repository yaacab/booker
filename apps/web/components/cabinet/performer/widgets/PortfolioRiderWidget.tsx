"use client";

import Link from "next/link";
import { categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import { usePerformerProfile } from "../usePerformerProfile";

type PortfolioRiderWidgetProps = {
  orgId: string;
  role: string;
};

export function PortfolioRiderWidget({ orgId, role }: PortfolioRiderWidgetProps) {
  const { profile, loading, error, canManage, publicHref, tariffBusy, addTariff } = usePerformerProfile(
    orgId,
    role,
  );

  const rider = profile?.rider || {};
  const hasRider = Boolean(rider.format || rider.lineup || rider.tech);

  return (
    <DashboardWidget
      title="Витрина и райдер"
      hint="Публичная страница и технические требования"
      accent="performer"
      isEmpty={!loading && !profile}
      empty="Создайте профиль в каталоге — откройте свободные слоты выше или в календаре."
    >
      {loading ? <p className="timeline">Загружаем витрину…</p> : null}
      {error && !profile ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}

      {profile ? (
        <>
          <ul className="timeline" data-testid="performer-portfolio-summary">
            <li>
              <strong>{profile.name}</strong> · {categoryLabel(profile.category)} · {profile.city}
            </li>
            {profile.verified ? <li>● Верификация пройдена</li> : <li>○ Верификация в процессе</li>}
            {profile.media_url ? (
              <li>
                ●{" "}
                <a href={profile.media_url} target="_blank" rel="noopener noreferrer">
                  Портфолио / медиа
                </a>
              </li>
            ) : (
              <li>○ Портфолио — добавьте ссылку через менеджера</li>
            )}
          </ul>

          <div className="card" style={{ marginTop: 12 }}>
            <p className="cabinet-eyebrow">Райдер</p>
            {hasRider ? (
              <ul className="timeline">
                {rider.format ? <li>Формат: {rider.format}</li> : null}
                {rider.lineup ? <li>Состав: {rider.lineup}</li> : null}
                {rider.tech ? <li>Техника: {rider.tech}</li> : null}
              </ul>
            ) : (
              <p className="timeline">Райдер уточняется в Deal Room после заявки.</p>
            )}
          </div>

          {profile.tariffs.length > 0 ? (
            <ul className="dashboard-list" style={{ marginTop: 12 }}>
              {profile.tariffs.map((t) => (
                <li key={t.id}>
                  <span>
                    {t.title} · {money(t.honorarium_rub)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {publicHref ? (
            <div className="cabinet-hero-actions" style={{ marginTop: 12 }}>
              <Link className="btn secondary" href={publicHref} data-testid="performer-public-link">
                Открыть публичную витрину
              </Link>
              <Link className="btn secondary" href={`${publicHref}#rider`}>
                Райдер на сайте
              </Link>
            </div>
          ) : null}

          {canManage ? (
            <form
              className="cabinet-inline-form"
              style={{ marginTop: 12 }}
              onSubmit={(e) => void addTariff(e)}
              data-testid="performer-tariff-form"
            >
              <strong>Добавить тариф</strong>
              <label>
                Название
                <input name="title" placeholder="DJ-сет 2 часа" required />
              </label>
              <label>
                Гонорар, ₽
                <input name="honorarium" type="number" min={1} required />
              </label>
              {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
              <button type="submit" disabled={tariffBusy}>
                {tariffBusy ? "Сохраняем…" : "Добавить тариф"}
              </button>
            </form>
          ) : null}
        </>
      ) : null}
    </DashboardWidget>
  );
}
