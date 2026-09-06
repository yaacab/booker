"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";
import {
  customerOnboardingItems,
  openOnboardingItems,
} from "@/lib/onboardingChecklists";

/** Customer onboarding checklist. Spec §5 / W2-ONBOARD. */
export function CustomerOnboardingWidget({
  hasName,
  hasContact,
  hasEventWithCity,
  hasOffers,
}: {
  hasName: boolean;
  hasContact: boolean;
  hasEventWithCity: boolean;
  hasOffers: boolean;
}) {
  const items = customerOnboardingItems({
    hasName,
    hasContact,
    hasEventWithCity,
    hasOffers,
  });
  const open = openOnboardingItems(items);
  if (open.length === 0) return null;

  return (
    <DashboardWidget title="Онбординг" hint="Чего не хватает" isEmpty={false}>
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
