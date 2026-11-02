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

## Tests

- `test_artist_tariff_crud.py` + `test_artist_profile_patch.py` + related publication/catalog: **37 PASS**
- Merge / push / production: NO-GO

## Still open (next thin slices)

- Service ↔ Tariff sync / public services discovery in web
- `PATCH/DELETE /services/{id}` + publish toggle
- Multi-artist org selector in cabinet
- Admin verification request from supply UI

Scores unchanged: FULL 59,00% / MVP 56,00% / Design 15,00%.
