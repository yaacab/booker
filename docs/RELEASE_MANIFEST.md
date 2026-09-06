# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06  
Branch: `feat/master-plan-execution`  
PR: #14 (OPEN — **не merge** без OK владельца)  
Prod deploy: **запрещён** до G3 / OK владельца

## Candidate SHA

Заполняется координатором на момент G2-ready:

- Integration SHA: `edf5b1a` (обновлять при каждом integrate)
- Evidence: CI checks на **этом** SHA / PR, не на старом `master`

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED | `fb24377` |
| Wave 1 search/SEO | VERIFIED | `6adf8c7` |
| Wave 2 deals/cabinets | PARTIAL | multi-hall `449e7e8`, cancel tests, cabinets depth WIP |
| Wave 3 discovery | PARTIAL | fav/briefs/share/compare; saved/promo WIP agents |
| Wave 4 trust/comms | PARTIAL | reviews/claim/support/outbox/msg hub |
| Wave 5 harden | PARTIAL | authz/e2e exist; screenshots/manifest draft |
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

- [ ] CI green on candidate SHA (unit + critical e2e)
- [ ] Screenshots 1440/390 × 3 roles
- [ ] Сквозной сценарий заявка→оффер на SHA
- [ ] E01–E24 table filled; E25 = ожидает G3
- [ ] No open mandatory A/B (OWNER_BLOCKED ≠ done)

## Explicit non-goals this package

- Merge to `master`
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
