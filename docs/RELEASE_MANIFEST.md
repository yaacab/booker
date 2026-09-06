# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06  
Branch: `feat/master-plan-execution`  
PR: #14 (OPEN — **не merge** без OK владельца)  
Prod deploy: **запрещён** до G3 / OK владельца

## Candidate SHA

Заполняется координатором на момент G2-ready:

- Integration SHA: `ef1f83b` (обновлять при каждом integrate)
- Evidence: CI checks на **этом** SHA / PR, не на старом `master`

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED | `fb24377` |
| Wave 1 search/SEO | VERIFIED | `6adf8c7` |
| Wave 2 deals/cabinets | PARTIAL | multi-hall `449e7e8`; cancel; cab depth; deal-path e2e in flight |
| Wave 3 discovery | MOSTLY | fav/briefs/share/compare/saved/promo |
| Wave 4 trust/comms | MOSTLY | reviews/claim/support/outbox/msg hub |
| Wave 5 harden | PARTIAL | CI e2e expand; a11y/backup proofs; screenshots/E-table in flight |
| E25 prod smoke | ожидает G3 | — |

## Contour C (disabled for G2 OK)

| Integration | G2 rule |
| ----------- | ------- |
| Live PSP | disabled / OWNER_BLOCKED — stub ≠ real PSP |
| Map provider | list-only without key |
| SMS/push | disabled transports |
| Signed legal | not claimed live |

## Rollback

1. URL-only Event Studio: `?event_studio_map_v1=0` (не глобальный откат)
2. Global flag: unset/`0` `NEXT_PUBLIC_EVENT_STUDIO_MAP_V1` + **rebuild web**
3. App rollback: redeploy previous known-good web/api images/SHA (only with owner OK on prod)

## Evidence checklist (G2)

- [ ] CI green on candidate SHA (unit + critical e2e) — list expanded: flow, cabinets-cross-role, cabinet-a11y (+ deal-path after integrate)
- [ ] Screenshots 1440/390 × 3 roles — in flight (`docs/screenshots/g2-roles/`)
- [x] Сквозной сценарий заявка→оффер на SHA — `apps/web/e2e/flow.spec.ts` + `cabinets-cross-role.spec.ts`; API `test_offers.py`
- [ ] E01–E24 table filled; E25 = ожидает G3 — `docs/E01_E24_EVIDENCE.md` in flight
- [ ] No open mandatory A/B (OWNER_BLOCKED ≠ done) — onboarding/autosave/deal e2e polish remain

### Proof pointers (a11y / backup)

| Check | Evidence | Result |
| ----- | -------- | ------ |
| E24 a11y cabinets | `apps/web/e2e/cabinet-a11y.spec.ts` | present; expand 390×3 roles in flight |
| E23 backup/restore | `apps/api/tests/test_backup_restore.py` + `docs/ops/RESTORE_DRILL_LOG.md` (2026-09-06 PASS) | unit PASS locally; drill PASS isolated `/tmp` |
| Hold exclusivity E09 | `apps/api/tests/test_hold_race.py` | PASS |
| Offer version E08 | `apps/api/tests/test_quote_versioning.py` | PASS |

## Explicit non-goals this package

- Merge to `master`
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
