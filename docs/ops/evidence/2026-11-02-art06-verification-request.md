# Evidence — ART-06 artist verification request

**Date:** 2026-11-02  
**Branch:** `feat/v4-offer-versions-audit`  
**Level:** локально  

## Scope

Supply-initiated verification request from artist cabinet into admin queue.

## Changes

- `POST /artists/{id}/verification-request` (org writer): creates `Verification(status=queued)`, audit `verification.requested`, idempotent while queued
- Private `GET /artists/{id}`: `can_request_verification`, `verification_request_queued`
- Admin decide closes queued rows instead of leaving orphans
- Cabinet CTA «Запросить проверку профиля»

## Verification

```bash
pytest tests/test_artist_verification_request.py \
  tests/test_admin.py::test_list_verifications_includes_pending_venues \
  tests/test_admin.py::test_verification_rejects_unknown_target_type -q
# 5 passed
```
