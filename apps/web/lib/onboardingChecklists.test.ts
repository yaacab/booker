import assert from "node:assert/strict";
import test from "node:test";
import {
  customerOnboardingItems,
  openOnboardingItems,
  performerOnboardingItems,
  venueOnboardingItems,
} from "./onboardingChecklists.ts";

test("customer checklist lists §5 gaps without fake %", () => {
  const items = customerOnboardingItems({
    hasName: true,
    hasContact: true,
    hasEventWithCity: false,
    hasOffers: false,
  });
  const open = openOnboardingItems(items);
  assert.ok(open.some((i) => i.id === "event"));
  assert.ok(open.some((i) => i.id === "search"));
  assert.ok(open.some((i) => i.id === "offer"));
  assert.equal(
    open.find((i) => i.id === "event")?.label.includes("%"),
    false,
  );
});

test("customer checklist hides when journey complete", () => {
  const open = openOnboardingItems(
    customerOnboardingItems({
      hasName: true,
      hasContact: true,
      hasEventWithCity: true,
      hasOffers: true,
    }),
  );
  assert.equal(open.length, 0);
});

test("performer and venue checklists stay step lists", () => {
  assert.equal(
    openOnboardingItems(
      performerOnboardingItems({
        profileComplete: false,
        hasOpenSlots: false,
        hasRequests: false,
      }),
    ).length,
    3,
  );
  assert.equal(
    openOnboardingItems(
      venueOnboardingItems({
        hasHalls: true,
        profileComplete: true,
        hasRequests: false,
      }),
    ).length,
    1,
  );
});
