"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";
import {
  openOnboardingItems,
  performerOnboardingItems,
} from "@/lib/onboardingChecklists";

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
  const items = performerOnboardingItems({
    profileComplete,
    hasOpenSlots,
    hasRequests,
  });
  if (openOnboardingItems(items).length === 0) return null;

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
