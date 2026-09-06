"use client";

import Link from "next/link";
import { DashboardWidget } from "../../DashboardWidget";
import {
  openOnboardingItems,
  venueOnboardingItems,
} from "@/lib/onboardingChecklists";

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
  const items = venueOnboardingItems({
    hasHalls,
    profileComplete,
    hasRequests,
  });
  if (openOnboardingItems(items).length === 0) return null;

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
