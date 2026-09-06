"use client";

import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerBooking } from "../types";
import { usePerformerCalendarOverview } from "../usePerformerCalendarOverview";

type CalendarOverviewWidgetProps = {
  orgId: string;
  artistId: string;
  bookings: PerformerBooking[];
};

export function CalendarOverviewWidget({ orgId, artistId, bookings }: CalendarOverviewWidgetProps) {
  const { openSlots, busySlots, activeVacation, confirmedDates, loading, error } = usePerformerCalendarOverview(
    orgId,
    artistId,
    bookings,
  );

  return (
    <DashboardWidget
      title="Обзор календаря"
      hint="Открытые вечера, занятость и отпуск"
      accent="performer"
      span="full"
      isEmpty={!loading && openSlots.length === 0 && busySlots.length === 0 && !activeVacation}
      empty="Откройте свободные слоты — без них вас нет в поиске на дату."
    >
      {loading ? <p className="timeline">Загружаем календарь…</p> : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}

      <ul className="timeline" data-testid="performer-calendar-overview">
        <li>Открытых слотов: {openSlots.length}</li>
        <li>Подтверждённых дат: {confirmedDates}</li>
        {activeVacation ? (
          <li>
            ● Отпуск до {activeVacation.ends_at ? formatWhen(activeVacation.ends_at) : "—"} — профиль скрыт из
            поиска
          </li>
        ) : (
          <li>○ Отпуск не активен</li>
        )}
      </ul>

      {openSlots.length > 0 ? (
        <>
          <p className="cabinet-eyebrow" style={{ marginTop: 12 }}>
            Ближайшие свободные
          </p>
          <ul className="dashboard-list">
            {openSlots.slice(0, 5).map((s) => (
              <li key={s.id}>
                <span className="mono">
                  {formatWhen(s.starts_at)} — {formatWhen(s.ends_at)}
                </span>
                <span className="chip ok">открыт</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {busySlots.length > 0 ? (
        <>
          <p className="cabinet-eyebrow" style={{ marginTop: 12 }}>
            Занято / удержания
          </p>
          <ul className="dashboard-list">
            {busySlots.map((s) => (
              <li key={s.id}>
                <span className="mono">{formatWhen(s.starts_at)}</span>
                <span className="chip wait">{s.status}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <p className="timeline" style={{ marginTop: 12 }}>
        <Link href="#cabinet-supply-heading">Импорт iCal и отпуск →</Link>
      </p>
    </DashboardWidget>
  );
}
