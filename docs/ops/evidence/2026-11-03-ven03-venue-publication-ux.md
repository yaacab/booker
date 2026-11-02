# Evidence — VEN-03 venue publication/photos UX

**Date:** 2026-11-03  
**Branch:** `feat/v4-offer-versions-audit`  
**Level:** локально  

## Scope

Паритет кабинета площадки с артистом по фото и публикации.

## Changes

- `GET /venues/{id}` (owner): `publication_*`, `calendar_confirmed_through`
- `VenuePhotosWidget` + `VenuePublicationWidget` на home кабинета площадки
- `useVenueProfile` для evidence/photos/toggle

## Verification

```bash
pytest tests/test_halls.py -q
# 6 passed
```
