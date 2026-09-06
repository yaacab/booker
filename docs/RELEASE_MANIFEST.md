# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06  
Branch: `feat/master-plan-execution`  
PR: #14 (OPEN — **не merge** без OK владельца)  
Prod deploy: **запрещён** до G3 / OK владельца

## Candidate SHA

- Integration SHA: `2037a7a` (`2037a7ac2f157106e1a66104e3a51983017a6ec7`)
- Evidence: CI checks на **этом** SHA / PR, не на старом `master`

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED | `fb24377` |
| Wave 1 search/SEO | VERIFIED | `6adf8c7` |
| Wave 2 deals/cabinets | MOSTLY | deal-path e2e E07–E09; onboard/autosave; cab depth |
| Wave 3 discovery | MOSTLY | fav/briefs/share/compare/saved/promo |
| Wave 4 trust/comms | MOSTLY | reviews/claim/support/outbox/msg hub |
| Wave 5 harden | MOSTLY | CI e2e expand; a11y 390×3; screenshots; E-table; backup proof |
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

- [ ] CI green on candidate SHA (unit + critical e2e) — list expanded on `2037a7a`; **await PR checks green**
- [x] Screenshots 1440/390 × 3 roles — `docs/screenshots/g2-roles/` (capture base `ef1f83b`, integrated `2037a7a`)
- [x] Сквозной сценарий заявка→оффер на SHA — `e2e/flow.spec.ts` + `e2e/deal-path.spec.ts` + `cabinets-cross-role.spec.ts`
- [x] E01–E24 table filled; E25 = ожидает G3 — `docs/E01_E24_EVIDENCE.md`
- [ ] No open mandatory A/B — residual PARTIAL depth (E01 guest→login, E06 offline, E12/E14 live PSP OWNER_BLOCKED ≠ A/B code gaps); Contour C stays disabled

### Proof pointers (a11y / backup)

| Check | Evidence | Result |
| ----- | -------- | ------ |
| E24 a11y cabinets | `apps/web/e2e/cabinet-a11y.spec.ts` (390×3 roles) | expanded |
| E23 backup/restore | `apps/api/tests/test_backup_restore.py` + `docs/ops/RESTORE_DRILL_LOG.md` (2026-09-06 PASS) | PASS |
| Hold exclusivity E09 | API `test_hold_race.py` + e2e `deal-path` E09 | covered |
| Offer version E08 | API `test_quote_versioning.py` + e2e `deal-path` E08 | covered |

## Explicit non-goals this package

- Merge to `master`
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
