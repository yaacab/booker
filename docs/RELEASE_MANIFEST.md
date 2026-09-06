# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06
Branch: feat/master-plan-execution
PR: #14 (OPEN — не merge без OK владельца)
Prod deploy: запрещён до G3 / OK владельца

## Candidate SHA

- Integration SHA: 321a2d8 (321a2d844adc5dbec37c824935ffddc1445fd3a5)
- Evidence: CI checks на этом SHA / PR, не на старом master
- Schema revision (Alembic head): `b1c2d3e4f5a7` (saved_searches)
- Payment mode: stub (`BOOKER_PAYMENT_PROVIDER=stub`, live disabled)
- Flags: `NEXT_PUBLIC_EVENT_STUDIO_MAP_V1` default OFF; composition_v2 / workspace_switcher on
- Notifications: email/sms/push disabled transports; in_app=dev
- Explicit: stub ≠ real PSP; map key / SMS — Contour C OWNER_BLOCKED

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED | fb24377 |
| Wave 1 search/SEO | VERIFIED | 6adf8c7 + search-persist e2e |
| Wave 2 deals/cabinets | VERIFIED | deal-path E07-E09; onboard; autosave; cab customer/performer/venue e2e |
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

- [ ] CI green on candidate SHA (unit + critical e2e) — local cab/E01/deal/org PASS; await GitHub after push
- [x] Screenshots 1440/390 x 3 roles — docs/screenshots/g2-roles/ (6 PNGs)
- [x] Сквозной сценарий заявка→оффер — e2e/flow.spec.ts + e2e/deal-path.spec.ts + cabinets-cross-role.spec.ts
- [x] E01-E24 table filled; E25 = ожидает G3 — docs/E01_E24_EVIDENCE.md
- [ ] No open mandatory A/B — Wave2 cab VERIFIED; E12/E14 stub PARTIAL vs live Contour C OWNER_BLOCKED → G2 remains open until CI green + Contour C policy accept

### Proof pointers

| Check | Evidence | Result |
| ----- | -------- | ------ |
| E24 a11y | cabinet-a11y.spec.ts 390x3 | PASS local |
| E23 backup | test_backup_restore.py + RESTORE_DRILL_LOG | PASS |
| E07-E09 | deal-path.spec.ts | PASS local |
| E01 | search-persist.spec.ts (UI login + 429 retry) | PASS local |
| E15 | org-switch.spec.ts (session pin) | PASS local |
| E06 | studio-autosave.spec.ts | PASS local |
| W2 cab depth | cabinet-customer/performer/venue.spec.ts | PASS local; in CI |

## Explicit non-goals

- Merge to master
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
