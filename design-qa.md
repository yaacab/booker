# BukerGo reference redesign — 2026-09-07

final result: blocked

This report supersedes earlier iteration notes. Code has been rebuilt across the
site, but this is not a passed whole-site visual acceptance or a production release.
The owner authorized publication. Deployment is blocked by missing SSH capability
in this environment, not by a claim that the VPS is offline.

## Visual source

Ten owner-uploaded JPEG reference sheets: D670 (catalog), 23F (public profiles),
43F (workspaces/favorites/saved searches), 72F/A7A (calendars/requests/services),
5D2 (Studio/events/briefs), B14 (shortlist/deals/login/profile), F7C (support/FAQ/legal),
E68/3D5 (legal documents). Files were inspected locally. Existing brand puzzle
photographs are decorative; real supplier cards only use published API media.

## Implemented compositions

| Area | Concrete changes | Evidence |
| --- | --- | --- |
| Catalog and profiles | Segmented search, category sidebar, puzzle-cut media, photo/content columns, factual summaries and booking area | `apps/web/app/catalog-reference-v2.css`, `CatalogFilters`, `CatalogResultCard`, `ArtistProfileClient`, `VenueProfileClient` |
| Role workspaces | Section-specific headings, metrics, next event, sidebar icons, secondary configuration disclosures | `components/cabinet/**`, `workspace-reference-v2.css` |
| Calendar | Performer month/list views, venue weekly hall matrix, month navigation, selected-day inspector, timezone labels | `MonthCalendar`, `VenueMonthCalendar`, `lib/calendarMonth.test.ts` |
| Requests/messages | Master/detail requests with real status groups; conversation rows | `RequestsInboxWidget`, `MessagesHubClient` |
| Studio | Editable basics, puzzle selection, actual selected team, requirements, budget footer, catalog drawer | `components/event-studio/**` |
| Deals/events | Progress, participants, tabbed content, confirmation/quote hierarchy and accessible mobile sheets | `app/deals/[id]/page.tsx`, `app/events/[id]/page.tsx`, `deal-reference-v2.css` |
| Favorites/shortlists/compare | Real profile cards, type filters, selection and comparison table, safe empty states | `FavoritesListClient`, `SharedShortlistClient`, `app/compare/page.tsx` |
| Saved searches | Compact rows, notification switches preserving explicit consent, secondary creation form | `app/cabinet/customer/saved-searches/page.tsx`, `saved-searches-reference-v2.css` |
| Account/briefs | Account identity and workspace columns; brief cards, search and labelled publish form with chosen dates | `app/profile/page.tsx`, `app/briefs/page.tsx` |
| Help/legal/login | Reference typography, decorative puzzle strip, FAQ search and audience filters, support form/statuses, document list/contents and glass login | `chrome-reference-v2.css`, corresponding routes |
| Global states | Consistent loaders/errors/footer; role-neutral pending navigation; readable API errors without HTML/server exception bodies | `PageLoading`, `SiteChrome`, `lib/api.test.ts` |

## Browser evidence and corrections

Preview: terminal.local:4173 (local supervised Next.js preview; not production).
Desktop screenshots were inspected at 1348 x 926. Narrow checks used a 390px iframe
(375px content width with scrollbar), not a real phone or an emulated device.

- FAQ: search returns explicit no-results state; role filter returns nine venue
  answers; disclosure opens. Narrow FAQ had equal clientWidth/scrollWidth (375px).
- Support: public login/contact state and decorative puzzle strip inspected.
- Catalog: search controls and error state inspected. API-connected results were
  not available in the preview.
- Studio: title edit reached saved state and survived reload. Mobile catalog opens
  as a dialog and closes with Escape. Rechecked corrected translucent backdrop,
  flat stage controls and readable puzzle labels. Date input persistence was not
  established in the browser pass; two simultaneous drafts and native input
  automation made that observation inconclusive.
- Calendar/requests: a temporary explicitly labelled synthetic component fixture
  rendered the real widgets. Selecting September 23 showed a booking ending at
  02:00 on September 24; new-request filtering selected its matching detail.
  These are component checks, not authenticated end-to-end role workflows.
- Screenshot findings corrected: inherited button shadows/backdrops; crowded
  puzzle labels; narrow calendar status wrapping (now dots with full accessible
  labels and selected-day detail); wrong-role links during pending role lookup;
  long support subjects overflowing; notification Escape focus stealing.
- Motion uses transform/opacity, scoped transitions and reduced-motion rules.
  Main puzzle layers no longer request permanent will-change. Real device FPS,
  reduced-motion emulation and full keyboard traversal were not measured.

Screenshot files emitted by the cloud browser did not synchronize to local scratch;
no broken file links are included. Source and implementation were visually
inspected in the session, but a saved normalized combined comparison for this
iteration is missing. This required fidelity gate remains blocked.

## Verification

- Frontend unit suite: 47 passed, including calendar boundary/status behavior,
  readable contrast tokens, puzzle state transitions, idempotency and safe errors.
- TypeScript: passed.
- Production build: passed for all existing routes. No local fixture route in the build output. Autoprefixer reported a non-fatal `align-items: start` compatibility warning in Studio CSS.
- API suite: 200 passed, 2 skipped, 2 dependency deprecation warnings. Dependencies
  were installed in the ignored local virtualenv and the complete suite was rerun.
- Static agent review: original deal/event endpoint templates and saved-search
  handlers/confirm/consent retained. Catalog SSR checks covered 12 context fields,
  unknown categories, travel=false and missing/synthetic media.
- The existing mobile e2e assertion was updated from complementary to dialog.
  Full Playwright E01–E25 was not run in this environment.
- Temporary fixture and mobile harness were removed before production build.

## Remaining gates

1. Seeded, API-connected screenshots of every role, profile, deal and populated
   catalog/shortlist state, with normalized side-by-side reference comparison.
2. Full authenticated user paths, mobile keyboard/reduced motion and device
   animation performance. Do not infer these from component fixtures or tsc.
3. Production preflight, effective runtime configuration, backup, staged build,
   release switch and post-deploy verification on the VPS. See
   `docs/ops/DESIGN_RELEASE_RUNBOOK.md`. No master merge, DNS or payments changes.

## Reference completion follow-up — 2026-09-08

The ten newly attached numbered sheets were opened in this session. They confirm
this same visual direction. Additional implementation:

- Both profile-sharing routes: split title/benefits and real profile preview,
  published media/facts, segmented sharing modes, compact QR/link controls,
  request cancellation, retry and clipboard fallback. Existing UTM/hall/tariff
  links and analytics remain intact.
- Operator: real queue counts, searchable profile rows, section navigation,
  journal table, existing metrics/payment/second-factor forms. All request
  endpoints and mutation payloads preserved. Removed the duplicate outer role
  sidebar on this route. No invented dispute queue or metric counts.
- Legal documents: extracted existing title, added branded photographic strip,
  preserved every source block and original section IDs/legal notices.
- Root error: neutral copy and matching palette; removed unsupported assurance
  about data integrity. Removed permanent puzzle will-change; fixed Studio CSS
  flex alignment compatibility warning.

Browser evidence: desktop 1348 x 926; a 390 x 780 iframe for narrow layout
(the rendered content excludes a scrollbar). Sharing error state, successful QR
render, source switching, manual-copy fallback and operator journal switching
were exercised. Legal document title, images and body rendered. Narrow sharing
and operator views were inspected visually. Browser frame DOM size measurement
was unavailable, so no automated overflow measurement is claimed. No auth or
production state was changed. Temporary mobile harness was removed.

The observed error log entries were from the browser extension. This is not a
claim that every route has no console errors. Populated profile/queue states and
normalized same-state source/implementation comparisons remain unverified;
therefore the whole-site result remains **blocked**, not completed acceptance.
The current changes add no generated supplier identities, reviews or ratings.

Verification: TypeScript passed; 47 frontend unit tests passed. Production build
result recorded below after completion. API was unchanged in this follow-up;
the 200 passing / 2 skipped API result above belongs to the previous iteration.

Follow-up production build: passed (36 static pages plus dynamic routes). One
non-fatal existing Autoprefixer warning remains for `align-items: end` in Studio.
