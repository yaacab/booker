# RELEASE_MANIFEST — Букер G2 candidate (draft)

Updated: 2026-09-06  
Branch:   
PR: #14 (OPEN — **не merge** без OK владельца)  
Prod deploy: **запрещён** до G3 / OK владельца

## Candidate SHA

- Integration SHA:  ()
- Evidence: CI checks на **этом** SHA / PR, не на старом 

## Scope A+B (статус)

| Область | Статус | Evidence |
| ------- | ------ | -------- |
| Wave 0 flag/CI/nav | VERIFIED |  |
| Wave 1 search/SEO | VERIFIED |  + E01 persist e2e |
| Wave 2 deals/cabinets | MOSTLY | deal-path E07–E09; onboard; autosave/offline; cab depth |
| Wave 3 discovery | MOSTLY | fav/briefs/share/compare/saved/promo |
| Wave 4 trust/comms | MOSTLY | reviews/claim/support/outbox/msg hub |
| Wave 5 harden | MOSTLY | CI e2e expanded; a11y 390×3; screenshots; E-table; backup |
| E25 prod smoke | ожидает G3 | — |

## Contour C (disabled for G2 OK)

| Integration | G2 rule |
| ----------- | ------- |
| Live PSP | disabled / OWNER_BLOCKED — stub ≠ real PSP |
| Map provider | list-only without key |
| SMS/push | disabled transports |
| Signed legal | not claimed live |

## Rollback

1. URL-only Event Studio:  (не глобальный откат)
2. Global flag: unset/  + **rebuild web**
3. App rollback: redeploy previous known-good web/api images/SHA (only with owner OK on prod)

## Evidence checklist (G2)

- [ ] CI green on candidate SHA (unit + critical e2e) — local batches PASS; list includes deal-path/a11y/onboard/autosave/search-persist/org-switch; **await PR checks on **
- [x] Screenshots 1440/390 × 3 roles —  (6 PNGs)
- [x] Сквозной сценарий заявка→оффер на SHA —  +  + 
- [x] E01–E24 table filled; E25 = ожидает G3 — 
- [ ] No open mandatory A/B — residual PARTIAL only where Contour C / live limits (E12/E14); E01/E06/E15 closed in e2e on this branch

### Proof pointers (a11y / backup)

| Check | Evidence | Result |
| ----- | -------- | ------ |
| E24 a11y cabinets |  (390×3 roles) | PASS local |
| E23 backup/restore |  +  | PASS |
| E07–E09 deal-path |  + API hold/quote | PASS local |
| E01 persist |  | merged |
| E15 org switch |  | merged |
| E06 autosave/offline |  | merged |

## Explicit non-goals this package

- Merge to 
- Production deploy to bukergo.ru
- Claiming live payment / map / SMS readiness
