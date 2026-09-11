# Artist-first readiness — 11 September 2026

Working branch: `codex/artist-first-readiness`. This checkpoint is not a production deployment or a statement of full readiness.

## Integrated source

- `7bcb55e` preserves the original local venue research and moderation/lifecycle work.
- `76c621b` merges the chrome editions, assembly, Moscow map, private development access and mobile improvements from `origin/fix/mobile-filters-demo-calendar`.
- The original dirty checkout remains untouched. Work is isolated in `outputs/readiness-worktree`.

## Implemented

- Homepage variant 02: work for artists / artists for events, three shaped chrome puzzle pieces, selection animation, light and Black editions, reduced-motion support. Venue and event assembly links are secondary.
- Role-aware registration links. Public navigation: artist search, work search, how it works.
- Venue-only district, metro, capacity and seating filters.
- Public order response form, specialization/search, artist response history including closed orders, customer response list and artist profile link. Protected history endpoint verifies organization membership.
- Shared deal card in both cabinets: event date, participants, server status, party expected to act, hold expiry, server price, last message and one link to continue.
- Incoming requests and negotiations are prioritized. Created proposals remain visible before artist acknowledgement. Archived requests are excluded from new requests. Agreed offers lead to holding the date.
- Profile action overflow fixed; chrome labels remain dark in Black Edition; compact mobile header.

## Completed checks

- Final production build and TypeScript check passed. Frontend unit suite: 48 passed after cabinet edits.
- Full API suite: 206 passed, 2 skipped. Includes new protected response history and shared summary assertions, hold expiry/conflict and authorization coverage. Two warnings concern the installed test client's deprecated integration.
- Browser: two passing tests in `apps/web/e2e/readiness.spec.ts`. Homepage at 1440/768/390 pixels in both themes and reduced motion. Isolated two-role flow: search → profile → UI request → UI offer → acknowledgements → message → hold; identical API quote/status/hold for both parties. Both cabinets checked at 390 pixels. Public order creation, artist response, owner review and closed response history also passed.
- Venue validator: 300 valid records / 300 unique sources. External images were not rechecked online in this run.

Browser tests require separately running web and API against an isolated database; never point them at production. `playwright.readiness.config.ts` defaults to web `127.0.0.1:4316`, API `127.0.0.1:8035`. Override with `BOOKER_WEB_URL`, `BOOKER_API_URL`, and optionally `BOOKER_BROWSER_EXECUTABLE`. Traces may contain test session tokens and are ignored by Git.

## Remaining before release

1. Audit the legacy date convention. `lib/format.ts` interprets naive API datetimes as Moscow wall time; `security.aware()` interprets naive database datetimes as UTC. SQLite drops supplied offsets, and slot/event input paths differ. The shared-flow test verifies both parties agree but does not establish correct UTC/Moscow conversion. Verify round trips, hold TTL and existing production data semantics before changing them or publishing.
2. Finish visual review of the profile, request and deal screens at mobile/tablet widths in both themes; the current browser checks are not a full page-by-page review.
3. Verify missing-supplier priorities, private development role hints and the selected release against actual production API/schema. Apply the dedicated release and rollback procedure; do not use the legacy script that seeds production.
4. Keep production payments disabled until the existing legal and partner gates are satisfied. Keep the demo gateway on its private service only.

Preview screenshots are local working artifacts under `/home/art67/booker/outputs/artist-first-preview`; they do not prove deployment to bukergo.ru.
