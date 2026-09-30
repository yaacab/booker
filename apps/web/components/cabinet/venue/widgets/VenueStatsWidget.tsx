"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";
import type { VenueBookingStats } from "../types";

type Props = {
  stats: VenueBookingStats;
  requestCount: number;
};

export function VenueStatsWidget({ stats, requestCount }: Props) {
  const conversion =
    requestCount > 0 ? Math.round((stats.total / requestCount) * 100) : null;

  return (
    <DashboardWidget
      title="Бронирования"
      hint="Заявки, подтверждённые и завершённые бронирования"
      accent="venue"
      span="full"
      isEmpty={stats.total === 0 && requestCount === 0}
      empty="Пока нет бронирований и заявок — статистика появится после первых запросов."
    >
      <div className="cabinet-metrics cabinet-metrics-inline">
        <article className="cabinet-metric tone-default">
          <p className="cabinet-metric-value">{stats.total}</p>
          <p className="cabinet-metric-label">Всего броней</p>
        </article>
        <article className={`cabinet-metric tone-${stats.confirmed ? "ok" : "default"}`}>
          <p className="cabinet-metric-value">{stats.confirmed}</p>
          <p className="cabinet-metric-label">Подтверждено</p>
        </article>
        <article className={`cabinet-metric tone-${stats.upcoming ? "live" : "default"}`}>
          <p className="cabinet-metric-value">{stats.upcoming}</p>
          <p className="cabinet-metric-label">Ближайшие</p>
        </article>
        <article className={`cabinet-metric tone-${stats.negotiation ? "wait" : "default"}`}>
          <p className="cabinet-metric-value">{stats.negotiation}</p>
          <p className="cabinet-metric-label">В переговорах</p>
        </article>
        <article className="cabinet-metric tone-default">
          <p className="cabinet-metric-value">{stats.completed}</p>
          <p className="cabinet-metric-label">Завершено</p>
        </article>
        <article className="cabinet-metric tone-default">
          <p className="cabinet-metric-value">{conversion != null ? `${conversion}%` : "—"}</p>
          <p className="cabinet-metric-label">Конверсия заявок</p>
          <p className="cabinet-metric-hint">{requestCount} входящих</p>
        </article>
      </div>
      <p className="timeline">
        Просмотры профиля и занятость залов — в следующих итерациях. Сейчас данные только из{" "}
        <Link href="/cabinet/venue/requests">заявок и бронирований</Link>.
      </p>
    </DashboardWidget>
  );
}
