"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";

/** Customer onboarding checklist. Spec §5 / W2-ONBOARD. */
export function CustomerOnboardingWidget({
  hasEvents,
  hasOffers,
}: {
  hasEvents: boolean;
  hasOffers: boolean;
}) {
  const items = [
    { id: "event", label: "Создать событие с датой", done: hasEvents, href: "/events/new" },
    { id: "search", label: "Посмотреть каталог по слотам", done: hasEvents, href: "/search" },
    { id: "offer", label: "Дождаться предложения в Deal Room", done: hasOffers, href: "/cabinet/customer" },
  ];
  const open = items.filter((i) => !i.done);
  if (open.length === 0) return null;

  return (
    <DashboardWidget title="Онбординг" hint="С чего начать" isEmpty={false}>
      <ul className="timeline" data-testid="customer-onboarding">
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
