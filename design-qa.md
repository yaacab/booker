# Design QA — Event Studio Map v1

## Visual reference

- Source: `handoffs/event-studio-map-v1/reference.webp` from commit `4d0f954`.
- Target route: `/events/new?event_studio_map_v1=1`.
- Viewports: desktop `1440 × 900`, mobile `390 × 844`.

## Checklist

- [x] Feature flag keeps the classic 8-step wizard unchanged.
- [x] Event Studio uses a dedicated full-screen shell without duplicate site navigation.
- [x] Desktop keeps the rail, map, catalog, and summary in one compact composition.
- [x] Date and venue editing are progressive disclosures rather than permanently expanded forms.
- [x] Approved reference imagery replaces CSS-art and initials-only placeholders.
- [x] Tablet catalog is an accessible side drawer with backdrop dismissal.
- [x] Mobile catalog is a bottom sheet; the summary remains reachable above safe-area insets.
- [x] Keyboard focus, status text, labels, reduced motion, and close controls are preserved.
- [x] Budget remains explicitly indicative; final price is produced only by server offers.
- [x] Production build and TypeScript checks pass.

## Screenshot status

Desktop `1440 × 900` and mobile `390 × 844` captures live in `docs/screenshots/event-studio-map-v1/` and are refreshed by `apps/web/e2e/event-studio-map.spec.ts`.
