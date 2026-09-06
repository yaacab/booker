# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06  
Branch: feat/master-plan-execution  
PR: #14 (OPEN — не merge без OK владельца)  
Prod deploy: запрещён до G3 / OK владельца

## Candidate SHA

- Integration SHA: 7e7964d (7e7964dd6fe03da2549c02dd1827875f3cb4c758)
- Evidence: CI checks на этом SHA / PR, не на старом master

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED | fb24377 |
| Wave 1 search/SEO | VERIFIED | 6adf8c7 + search-persist e2e |
| Wave 2 deals/cabinets | MOSTLY | deal-path E07-E09; onboard; autosave/offline; cab depth |
| Wave 3 discovery | MOSTLY | fav/briefs/share/compare/saved/promo |
| Wave 4 trust/comms | MOSTLY | reviews/claim/support/outbox/msg hub |
| Wave 5 harden | MOSTLY | CI e2e expanded; a11y 390x3; screenshots; E-table; backup |
| E25 prod smoke | ожидает G3 | — |

## Contour C (disabled for G2 OK)

| Integration | G2 rule |
| ----------- | ------- |
| Live PSP | disabled / OWNER_BLOCKED — stub != real PSP |
| Map provider | list-only without key |
| SMS/push | disabled transports |
| Signed legal | not claimed live |

## Rollback

1. URL-only Event Studio: ?event_studio_map_v1=0 (не глобальный откат)
2. Global flag: unset/0 NEXT_PUBLIC_EVENT_STUDIO_MAP_V1 + rebuild web
3. App rollback: redeploy previous known-good web/api images/SHA (only with owner OK on prod)

## Evidence checklist (G2)

- [ ] CI green on candidate SHA (unit + critical e2e) — local batches PASS; list includes deal-path/a11y/onboard/autosave/search-persist/org-switch; await PR checks on 7e7964d
- [x] Screenshots 1440/390 x 3 roles — docs/screenshots/g2-roles/ (6 PNGs)
- [x] Сквозной сценарий заявка→оффер на SHA — e2e/flow.spec.ts + e2e/deal-path.spec.ts + cabinets-cross-role.spec.ts
- [x] E01-E24 table filled; E25 = ожидает G3 — docs/E01_E24_EVIDENCE.md
- [ ] No open mandatory A/B — residual PARTIAL only E12/E14 Contour C live limits; E01/E06/E15 closed in e2e

### Proof pointers (a11y / backup)

| Check | Evidence | Result |
| ----- | -------- | ------ |
| E24 a11y cabinets | apps/web/e2e/cabinet-a11y.spec.ts (390x3 roles) | PASS local |
| E23 backup/restore | test_backup_restore.py + docs/ops/RESTORE_DRILL_LOG.md | PASS |
| E07-E09 deal-path | e2e/deal-path.spec.ts + API hold/quote | PASS local |
| E01 persist | e2e/search-persist.spec.ts | merged |
| E15 org switch | e2e/org-switch.spec.ts | merged |
| E06 autosave/offline | e2e/studio-autosave.spec.ts | merged |

## Explicit non-goals this package

- Merge to master
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
