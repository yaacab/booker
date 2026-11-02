# Evidence — V4 Offer versions / Deal Room audit (DEAL-03)

**Date:** 2026-11-02  
**Branch:** `feat/v4-offer-versions-audit`  
**Level:** локально  

## Scope

Усиление версий условий оффера, статусов renegotiation и аудита изменений без live-платежей и без дизайна.

## Changes

- `GET /offers/{offer_id}/versions` — история версий + ack для участников сделки
- `POST /offers/{offer_id}/versions` — сброс `accepted_offer_version_id`, system message, audit с `previous_version_id` / delta
- `GET /deal-room/{booking_id}` — `offer_versions`, `offer_timeline`, `accepted_offer_version_id`, `renegotiation_pending`
- DB/ORM: коммерческие поля `OfferVersion` immutable; `customer_ack`/`supplier_ack` остаются mutable
- Web Deal Room: ack всегда с `quote_id`; вкладка «Условия» показывает историю версий

## Verification

```bash
cd apps/api
/home/art67/booker/apps/api/.venv/bin/pytest \
  tests/test_deal_offer_audit_v4.py \
  tests/test_offers.py \
  tests/test_quote_versioning.py -q
# 19 passed
```

## Out of scope / NO-GO

- Production merge/push
- Live payments / partner acquiring
- Design transfer / Artist vNext IA
