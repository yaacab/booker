"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";

/** Performer onboarding checklist. Spec §5 / W2-ONBOARD. */
export function PerformerOnboardingWidget({
  profileComplete,
  hasOpenSlots,
  hasRequests,
}: {
  profileComplete: boolean;
  hasOpenSlots: boolean;
  hasRequests: boolean;
}) {
  const items = [
    {
      id: "profile",
      label: "Заполнить профиль и портфолио",
      done: profileComplete,
      href: "/cabinet/performer#supply",
    },
    {
      id: "slots",
      label: "Открыть слоты в календаре",
      done: hasOpenSlots || hasRequests,
      href: "/cabinet/performer/calendar",
    },
    {
      id: "requests",
      label: "Ответить на входящую заявку предложением",
      done: hasRequests,
      href: "/cabinet/performer/requests",
    },
  ];
  if (items.every((i) => i.done)) return null;

  return (
    <DashboardWidget title="Онбординг" hint="Готовность к брони" isEmpty={false}>
      <ul className="timeline" data-testid="performer-onboarding">
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
