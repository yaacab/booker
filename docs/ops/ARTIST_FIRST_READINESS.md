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
- Upcoming events show missing artist roles with contextual search links. Artists see relevant open jobs by city and category. Cancelled bookings no longer fill staffing requirements.
- Profile, request, deal and both cabinets have readable Black Edition surfaces, buttons and calendars. Requests show artist names; the deal heading shows its event.
- Registration copy explains finding artists and work; role links select the correct account type.
- UTC is normalized before SQLite drops input offsets and attached on read. Moscow conversion is explicit; no historical date rows are rewritten. Completed-performance counts exclude merely confirmed future bookings; unsupported response-time claims were removed.

## Completed checks

- Final production build and TypeScript check passed. Frontend unit suite: 51 passed.
- Full API suite: 210 passed, 2 skipped. Includes protected response history, shared summary assertions, UTC round trips, hold expiry/conflict, completed-performance counts and authorization coverage. Two warnings concern the installed test client's deprecated integration.
- Browser: three passing tests in `apps/web/e2e/readiness.spec.ts`. Homepage at 1440/768/390 pixels in both themes and reduced motion. Isolated two-role flow: category/date search → profile → UI request → UI offer → acknowledgements → message → hold; identical quote/status/event date/hold for both parties and a real 24-hour TTL. Search, profile, request, deal and both cabinets checked at 1440/390 in both editions. Missing-role priorities, matching jobs, public order creation, artist response, owner review and closed response history passed. UI registration for each role creates its organization and opens the correct cabinet.
- Venue validator: 300 valid records / 300 unique sources. External images were not rechecked online in this run.

Browser tests require separately running web and API against an isolated database; never point them at production. `playwright.readiness.config.ts` defaults to web `127.0.0.1:4316`, API `127.0.0.1:8035`. Override with `BOOKER_WEB_URL`, `BOOKER_API_URL`, and optionally `BOOKER_BROWSER_EXECUTABLE`. Traces may contain test session tokens and are ignored by Git.

## Remaining before release

1. Rehearse additive venue schema initialization and old/new API compatibility on a private restored production database. Stage the exact reviewed commit and validate it before switching directories; never seed production.
2. Verify private development role hints and isolation against production, then perform the dedicated backup/switch/rollback and live acceptance procedure.
3. Preserve production external-payment mode and the existing legal/partner gates. Keep the demo gateway on its private service only.

## Production preflight evidence

- Live marker: `8ebf469`; all four public/private services active. API dependencies and web lockfile match the candidate byte-for-byte. Node 20.20.2 / npm 10.8.2.
- All 364 tracked baseline web/API files exist. Only a test differs (the server lacks newer district/metro assertions); no live-only application hotfix, local environment file, runtime data or symlink was found in the application directories. Generated egg-info is expendable; virtualenv/data/config remain in place.
- Read-only date audit: 1 event, 1 request, 0 bookings/holds, 5,277 slots (60 artist, 5,217 hall). Sources: 5,216 synthetic slots and 61 seed slots, no imported iCal/vacation offsets; seed and synthetic writers use UTC. The only event uses the slot-copying quick-request path. No historical offset conversion is needed; raw timestamps remain unchanged.
- The existing browser bundles leave Event Studio Map unset (default off). Candidate keeps it off; `/assemble` and its Moscow map remain available. Public API uses external payment; private demo uses stub. No payment or service-environment changes are part of this release.

Preview screenshots are local working artifacts under `/home/art67/booker/outputs/artist-first-preview`; they do not prove deployment to bukergo.ru.

## Published baseline and subsequent review

Baseline `5590ed7d890fd401e14678fc8ff7692783b8d5e6` was published on 11 September. Four services and thirteen public routes passed. Schema rehearsal preserved existing values; previous code could read the upgraded database copies. Private test tokens remain invalid against the public API. A subsequent burst revealed 71 SQLite connection-pool timeouts.

Current corrections: file SQLite uses request-scoped connections; concurrent favorites reads are shared per account/organization. Homepage now has two explicit role entries, a four-piece chrome composition, padded category/process cards and mobile role selection before decoration. “Артистам” leads to direction/city selection and useful empty-result actions. Login contrast and spacing are corrected. All four demo cards are visible separately, with copyable, explicitly test-only credentials; public passwordless access stays disabled.

Validation: local production build and TypeScript passed; 54 frontend tests, 212 API tests with 2 skips, five browser scenarios including shared deal, role registration, login contrast, test credential clipboard and artist empty results. Pending: candidate concurrent HTTP check and release acceptance. User-approved venue discovery with photos, source attribution, availability clarification and a real district map is still in progress. The overall goal is not complete.

## Venue review completed locally

The research selection is now connected to `/search?kind=venue`: 300 records, 24 visible initially, attributed photos, expandable galleries, guest/price/sound filters and a 132-district presentation map. Hover previews a district; clicking or selecting it filters cards. Full source coordinates identify 276 districts for 277 located venues; unmatched records remain in the general selection. No legacy production records were deleted. Research metadata remains noindex and cards do not offer booking.

The six browser scenarios passed, with a separate regression check confirming no hydration warning after rounding projected SVG attributes consistently across Node and Chromium. TypeScript passed. The isolated real HTTP load check completed 240/240 requests at concurrency 80 without errors (local machine, empty test database; this is not a production capacity claim). A production candidate and public acceptance still require release authorization.

Deployment must install **both** `data/moscow_performance_venues_research.json` and `data/moscow_venue_districts.json` beside the application root; the server-rendered discovery loader requires both. Map geometry ships in the web bundle. Keep the private demo gateway private and preserve external-payment configuration. Git push was rejected by automatic approval review even after the origin URL matched the user's GitHub reference; explicit publishing approval has been requested. No workaround publication was attempted.
