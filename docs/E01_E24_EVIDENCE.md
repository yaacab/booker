# E01–E24 Evidence — Spec v3 G2 candidate

**Candidate SHA:** `14b2c0dfbf7068d537cb1947e640192ed12f42c2` (`14b2c0d`)  
**Branch:** `feat/master-plan-execution`  
**Date:** 2026-09-06  
**G2 status:** **не закрыт** — evidence pack mostly landed; CI green on this SHA still required.  
**E25:** **ожидает G3** (prod smoke только с OK владельца).  
**Explicit non-claims:** live PSP / map provider / SMS-push **не** заявляются; stub ≠ real PSP.

Результаты: `PASS` | `PARTIAL` | `FAIL` | `OWNER_BLOCKED` | `ожидает G3`.

```bash
# API
cd apps/api && pytest -q tests/test_<name>.py

# Critical e2e (ci.yml e2e-critical)
cd apps/web && npx playwright test \
  e2e/event-studio-map.spec.ts \
  e2e/supply-nav.spec.ts \
  e2e/search-filters.spec.ts \
  e2e/flow.spec.ts \
  e2e/deal-path.spec.ts \
  e2e/cabinets-cross-role.spec.ts \
  e2e/cabinet-a11y.spec.ts \
  e2e/studio-autosave.spec.ts \
  e2e/onboarding.spec.ts
```

## Evidence table

| ID | Scenario | Command / test path | Result | SHA / evidence | Notes |
| ---- | ---- | ---- | ---- | ---- | ---- |
| E01 | Гость ищет артиста → входит | `test_catalog_search_filters.py`; `e2e/search-filters.spec.ts` | **PARTIAL** | `6adf8c7` | Filters/URL PASS; no dedicated guest→login restore e2e |
| E02 | Поиск зала 80 гостей | `test_search_venue_guests_matching_halls`; search-filters | **PASS** | `6adf8c7` | Map OWNER_BLOCKED ≠ list search |
| E03 | Синтетический календарь | synthetic flag API + e2e copy | **PASS** | `6adf8c7` | |
| E04 | Избранное без брони | `test_favorites.py` E04 | **PASS** | `8715009` | |
| E05 | Event Studio flag on/off | `e2e/event-studio-map.spec.ts` | **PASS** | `fb24377` | default OFF |
| E06 | Autosave / reload / offline | `e2e/studio-autosave.spec.ts`; event-studio-map E06 | **PARTIAL** | `14b2c0d` | Reload PASS; offline/retry thin |
| E07 | Заявка → оффер одна сущность | `e2e/deal-path.spec.ts` E07; flow; cross-role | **PASS** | `14b2c0d` | In CI critical list |
| E08 | Новая версия оффера | `test_quote_versioning.py`; deal-path E08 | **PASS** | `14b2c0d` | Old acks invalid until re-ack |
| E09 | Двойной hold | `test_hold_race.py`; deal-path E09 | **PASS** | `14b2c0d` | One 200 + one 409 |
| E10 | Multi-hall atomic | `test_multi_hall_atomic.py` | **PASS** | `449e7e8` | |
| E11 | Hold expire / cancel | holds + replacement + cross-role cancel | **PASS** | base | |
| E12 | Fake pay redirect / webhook | `test_payments.py` stub | **PARTIAL** | base | stub≠PSP; C-LIVE OWNER_BLOCKED |
| E13 | External-paid + audit | `test_external_payment_confirm.py` | **PASS** | `e578301` | |
| E14 | Refund idempotency | authz refunds | **PARTIAL** | base | full refund; live adapter OWNER_BLOCKED |
| E15 | Три роли | cabinets-cross-role; workspace | **PARTIAL** | base | cabinets PASS; org-switch UI thin |
| E16 | Календарь ≠ Заявки | `e2e/supply-nav.spec.ts` 390 | **PASS** | `fb24377` | |
| E17 | IDOR | authz / idor / halls / attachments | **PASS** | base | |
| E18 | Публичный бриф | `test_briefs.py` leak guard | **PASS** | `4bf519a` | |
| E19 | Отклик на бриф | briefs respond/close | **PASS** | `4bf519a` | |
| E20 | Reviews / claim | reviews + trust | **PASS** | `51214da` / `700f2c1` | |
| E21 | Email outbox retry | `test_email_outbox_retry_idempotent` | **PASS** | `700f2c1` | |
| E22 | Revoke shared link | `test_shortlists.py` revoke | **PASS** | `700f2c1` | |
| E23 | Backup restore | `test_backup_restore.py`; RESTORE_DRILL_LOG | **PASS** | drill 2026-09-06 | |
| E24 | 390 + keyboard | `cabinet-a11y.spec.ts`; `docs/screenshots/g2-roles/` | **PASS** | `14b2c0d` | Full SR audit still manual |
| E25 | Prod smoke | — | **ожидает G3** | — | |

## Manifest checkbox sources

| Checklist item | Evidence |
| ---- | ---- |
| CI green on candidate SHA | Expanded e2e-critical; await green on `14b2c0d` |
| Screenshots 1440/390 × 3 roles | `docs/screenshots/g2-roles/` (6 PNGs) |
| Заявка→оффер | flow + deal-path + cross-role |
| E01–E24 table | this file; E25 = ожидает G3 |
| No open mandatory A/B | Contour C OWNER_BLOCKED documented; residual PARTIAL depth remains → G2 not closed |
| a11y / backup | E24 / E23 rows |

## Counts

| Result | IDs |
| ---- | ---- |
| PASS | E02 E03 E04 E05 E07 E08 E09 E10 E11 E13 E16 E17 E18 E19 E20 E21 E22 E23 E24 |
| PARTIAL | E01 E06 E12 E14 E15 |
| OWNER_BLOCKED / Contour C | live PSP/map/SMS (not E-row closes) |
| ожидает G3 | E25 |
