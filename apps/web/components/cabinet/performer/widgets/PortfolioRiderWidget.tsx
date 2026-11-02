"use client";

import Link from "next/link";
import { useState } from "react";
import { categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import { usePerformerProfile } from "../usePerformerProfile";

type PortfolioRiderWidgetProps = {
  orgId: string;
  role: string;
};

export function PortfolioRiderWidget({ orgId, role }: PortfolioRiderWidgetProps) {
  const {
    profile,
    loading,
    error,
    canManage,
    publicHref,
    tariffBusy,
    addTariff,
    updateTariff,
    deleteTariff,
    updateRider,
  } = usePerformerProfile(orgId, role);
  const [editing, setEditing] = useState<string | null>(null);
  const [editingRider, setEditingRider] = useState(false);

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
            {editingRider && canManage ? (
              <form
                className="cabinet-inline-form"
                data-testid="performer-rider-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  if (
                    await updateRider({
                      format: String(data.get("format") || ""),
                      lineup: String(data.get("lineup") || ""),
                      tech: String(data.get("tech") || ""),
                      travel: String(data.get("travel") || ""),
                    })
                  ) {
                    setEditingRider(false);
                  }
                }}
              >
                <label>
                  Формат
                  <input name="format" defaultValue={rider.format || ""} placeholder="dj / live / duo" />
                </label>
                <label>
                  Состав
                  <input name="lineup" defaultValue={rider.lineup || ""} />
                </label>
                <label>
                  Техника
                  <input name="tech" defaultValue={rider.tech || ""} />
                </label>
                <label>
                  Выезд
                  <input name="travel" defaultValue={rider.travel || ""} placeholder="yes / no" />
                </label>
                <button type="submit" disabled={tariffBusy}>
                  Сохранить райдер
                </button>
                <button type="button" className="secondary" onClick={() => setEditingRider(false)}>
                  Отмена
                </button>
              </form>
            ) : hasRider ? (
              <ul className="timeline">
                {rider.format ? <li>Формат: {rider.format}</li> : null}
                {rider.lineup ? <li>Состав: {rider.lineup}</li> : null}
                {rider.tech ? <li>Техника: {rider.tech}</li> : null}
                {rider.travel ? <li>Выезд: {rider.travel}</li> : null}
                {canManage ? (
                  <li>
                    <button type="button" className="linkish" onClick={() => setEditingRider(true)}>
                      Изменить райдер
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : (
              <p className="timeline">
                Райдер пуст.{" "}
                {canManage ? (
                  <button type="button" className="linkish" onClick={() => setEditingRider(true)}>
                    Заполнить
                  </button>
                ) : (
                  "Уточняется в Deal Room после заявки."
                )}
              </p>
            )}
          </div>

          {profile.tariffs.length > 0 ? (
            <ul className="dashboard-list" style={{ marginTop: 12 }}>
              {profile.tariffs.map((t) => (
                <li key={t.id}>
                  {editing === t.id ? (
                    <form className="cabinet-inline-form tariff-edit" onSubmit={async (e) => { e.preventDefault(); const d = new FormData(e.currentTarget); if (await updateTariff(t.id, { title: String(d.get("title") || ""), honorarium_rub: Number(d.get("honorarium") || 0) })) setEditing(null); }}>
                      <label>Название<input name="title" defaultValue={t.title} required /></label>
                      <label>Гонорар, ₽<input name="honorarium" type="number" min={1} defaultValue={t.honorarium_rub} required /></label>
                      <button type="submit" disabled={tariffBusy}>Сохранить</button>
                      <button type="button" className="secondary" onClick={() => setEditing(null)}>Отмена</button>
                    </form>
                  ) : (
                    <span>
                      {t.title} · {money(t.honorarium_rub)}
                      {canManage ? <> <button type="button" className="linkish" onClick={() => setEditing(t.id)}>Изменить</button> <button type="button" className="linkish" disabled={tariffBusy} onClick={() => { if (window.confirm(`Удалить тариф «${t.title}»?`)) void deleteTariff(t.id); }}>Удалить</button></> : null}
                    </span>
                  )}
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
              <Link className="btn" href={`${publicHref}/share`} data-testid="performer-share-link">
                Поделиться / QR
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
