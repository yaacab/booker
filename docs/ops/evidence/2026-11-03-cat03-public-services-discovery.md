# Evidence — CAT-03 public services discovery

**Date:** 2026-11-03  
**Branch:** `feat/v4-offer-versions-audit`  
**Level:** локально  

## Scope

Публичный discovery услуг в web через каталог.

## Changes

- `GET /services/public` — фильтры `city`/`budget_max`, enrichment `profile_name`/`profile_href`/`profile_verified`/`media_url`
- `/search?kind=service` — выдача карточек услуг с переходом к профилю
- Навигация SiteChrome: ссылка «Услуги»

## Verification

```bash
pytest tests/test_services.py -q
# 10 passed
```
