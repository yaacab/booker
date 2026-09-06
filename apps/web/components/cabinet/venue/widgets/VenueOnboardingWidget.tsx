"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";

/** Venue onboarding checklist. Spec §5 / W2-ONBOARD. */
export function VenueOnboardingWidget({
  hasHalls,
  profileComplete,
  hasRequests,
}: {
  hasHalls: boolean;
  profileComplete: boolean;
  hasRequests: boolean;
}) {
  const items = [
    {
      id: "halls",
      label: "Добавить зал с вместимостью",
      done: hasHalls,
      href: "/cabinet/venue/calendar",
    },
    {
      id: "profile",
      label: "Заполнить профиль площадки",
      done: profileComplete,
      href: "/cabinet/venue#supply",
    },
    {
      id: "requests",
      label: "Ответить на заявку бронирования",
      done: hasRequests,
      href: "/cabinet/venue/requests",
    },
  ];
  if (items.every((i) => i.done)) return null;

  return (
    <DashboardWidget title="Онбординг" hint="Готовность площадки" isEmpty={false}>
      <ul className="timeline" data-testid="venue-onboarding">
        {items.map((item) => (
          <li key={item.id}>
            {item.done ? "●" : "○"}{" "}
            {item.done ? item.label : <Link href={item.href}>{item.label}</Link>}
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
