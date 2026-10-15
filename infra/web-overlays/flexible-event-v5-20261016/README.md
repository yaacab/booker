# BK-WEB-FLEX-020 — original v5 → real Event Studio

This hash-guarded patch targets the exact published mobile-layout-019 web source. Apply only to an isolated copy under a new release directory. The shared checkout contains unrelated work and is not the build source.

The original v5 ZIP and its App.tsx were compared byte for byte with the source used for extraction. The patch retains the original event canvas, seven freely ordered sections, paper flights, golden threads, calendar/time wheels and final assembly choreography. Prototype registration, fake suppliers, fake availability and fake success screens are excluded.

Both `/assemble` and default `/events/new` use the same existing EventStudioShell, draft storage, catalogue and submission adapter. Existing classic wizard is available with `?event_studio_map_v1=0`. Supplier IDs come from the API; stock images illustrate event formats only. Explicit deferred supplier selection does not invent resources or imply a booking. Budget is the customer's requested limit; API tariffs are displayed as indicative prices, never as a confirmed quote. Rider notes and end time are included in existing event notes.

Drafts remain device-local, as in the published baseline. The UI says so. Submission still requires the existing login; no API, database, OAuth, legal or payment gates are enabled. Final submission uses the existing API path, not the prototype's send animation.

Validation: TypeScript and production build; 72 unit tests including visual↔real draft mapping, external catalogue additions, requested budget/rider/API resource IDs and completed-submit retry. Chromium checks include free-order editing, date/time, narrow-screen summary, API error, login handoff and browser Back with draft restoration. Authenticated production booking, physical Safari/iOS/Android and frame-rate acceptance are not claimed.

Deployment requires the server's own tsc/unit/build, secret gate, browser preview, exact source/hash guards, saved unit override and rollback to mobile-layout-019. Public nginx/API/DB must not change. See the task's release report for the actual deployment outcome.
