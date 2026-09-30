# Mobile filter fixes

Based on edition branch commit 8ebf469bd296518d3860f73a01bb8d99cf5019b9.

- Explicit field backgrounds and readable lime button labels in both editions.
- Single-column mobile filter form; native radios and 44px option targets.
- Category changes apply with the submit button, preserving the rest of the form.
- Artist/venue switches discard incompatible categories.
- Catalog requests have an eight-second timeout; malformed list responses cannot be mapped as arrays.
- Private demo SSR uses the same isolated API as the demo gateway.

## Test calendar

BOOKER_DEMO_OPEN_CALENDAR=1 is added only to booker-demo-api.service.
It refuses any database other than SQLite /var/lib/booker-demo/demo.db.
Searching a date materializes daily open slots for demo artists and halls without
overwriting existing availability, holds, confirmed bookings, or busy dates.
This supports arbitrary requested dates, not unlimited simultaneous bookings.
Real calendars and payment configuration are unchanged. Do not enable on the public API.

## Validation / rollout

TypeScript typecheck passed. Python files compile. Backend pytest is blocked by
the restored environment's broken typing_extensions installation; rerun the guard
and catalog search tests with intact dependencies before deployment.
Mobile browser, production rollout, and actual booking-path checks are still required.
No production deployment was performed for this patch.
