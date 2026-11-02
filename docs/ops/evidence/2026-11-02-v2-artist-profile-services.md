# V2 — Artist Profile & Services (thin slice)

**Date:** 2026-11-02  
**Branch:** `feat/v2-artist-profile-services`  
**Worktree:** `/home/art67/booker-worktrees/v2-artist-profile-services`  
**Base:** `0bd7aa0` (independent of unmerged V0)

## Scope delivered

1. `PATCH/DELETE /artists/{id}/tariffs/{tariff_id}` — matches existing cabinet UI.
2. `TariffIn.honorarium_rub >= 1` validation.
3. `PATCH /artists/{id}` for name/city/category/rider_json.
4. Owner-facing publication fields on `GET /artists/{id}`; completeness exposes `resource_id` + publication state.
5. Cabinet `PublicationWidget` (evidence + publish toggle) + rider edit in `PortfolioRiderWidget`.
6. `media_url` in `/catalog/search` artist payloads (legacy + paginated).
7. `PATCH/DELETE /services/{id}`, publish toggle, `POST /services/{id}/sync-tariff`.
8. Services cabinet: bind profile, sync tariff, multi-artist selector (localStorage).

## Tests / review

- Focused V2 API suite: **50 PASS**
- Ruff on touched modules: PASS
- Independent security review: **PASS** (no CRITICAL/HIGH/MEDIUM)
- Merge / push / production: NO-GO

## Deferred

- Supply-initiated admin verification request (operator process remains admin-only)
- Public `/services/public` discovery page in web (catalog search remains primary)

Scores unchanged: FULL 59,00% / MVP 56,00% / Design 15,00%.
