# TASK LEDGER — Букер critical path

Единая очередь исполнения. План: [ops/DELIVERY_PLAN_2026-10-15.md](ops/DELIVERY_PLAN_2026-10-15.md).
Измерение: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md).

Статусы: `NOT_STARTED` | `IMPLEMENTED` | `VERIFIED` | `BLOCKED` | `FAILED` | `ACCEPTED`

Обновлено: 2026-10-15 (FINAL HANDOFF). Кандидаты CI PASS: delivery `402d812`, design `080fd4b`, MVP `bb61e998`. Handoff: `docs/ops/FINAL_DELIVERY_HANDOFF.md`.

| ID | Задача | Pri | Status | Evidence / note |
|---|---|---|---|---|
| A0–A3 | Stage A | P0 | ACCEPTED | prior — do not redo |
| B1a | Remote staging discovery | P0 | BLOCKED | DNS empty; owner B unused |
| B1b | Staging package | P0 | IMPLEMENTED | hardened — `2026-10-15-staging-hardened.md` |
| B1c | Fail-closed preflight + neg tests | P0 | VERIFIED | **21 PASS** `infra/test_staging_preflight.py` + A1 launcher finish |
| B1d | Host proposal (option C) | P0 | IMPLEMENTED | proposal + `STAGING_PROVISION_PLAYBOOK.md` — wait GO |
| B2a | LOCAL SQLite rehearsal | P0 | VERIFIED | prior — do not redo |
| C01–C10 | Local acceptance | P0 | VERIFIED | prior; C04/C08 deepened prior |
| S06a | Dual-admin recover deny | P0 | VERIFIED | prior local |
| S06b | Two-approver design+tests (flag OFF) | P0 | IMPLEMENTED | `2026-10-15-two-approver-design.md`; SMTP still BLOCKED |
| S06c | SMTP / staging recovery proof | P0 | BLOCKED | owner SMTP + host GO |
| T09a | Catalog pagination local tests | P1 | VERIFIED | 10 PASS LOCAL — score still ○ |
| T09b | Local catalog bench harness | P1 | IMPLEMENTED | `infra/catalog_bench_local.py` — no p95 claim |
| T11a | Authz/privacy + fake AV local | P1 | VERIFIED | prior + IDOR expand |
| T13a | Ops prep / runbook for future host | P1 | IMPLEMENTED | LOCAL prep only |
| F-duty | Support duty runbook | P1 | IMPLEMENTED | `SUPPORT_DUTY_RUNBOOK.md` — no real users |
| M06-prep | Legal consistency pack | P1 | IMPLEMENTED | `CONSISTENCY_REVIEW_2026-10-15.md` — no publish |
| M07-prep | Payment sandbox race harden | P1 | IMPLEMENTED | webhook fail-closed races LOCAL; live BLOCKED |
| D02 | Design tokens + motion packet | P1 | IMPLEMENTED | branch `cursor/design-system-cbf8` — UNAPPROVED |
| OWN1 | Owner packet | P0 | ACCEPTED | A/B/C recorded; wait C GO |
| F1 | Production GO/NO-GO | P0 | ACCEPTED | **NO-GO** |
| CI22 | Mandatory CI #22 `402d812` | P0 | VERIFIED | run 38681811296 — PASS 5/5 |
| CI23 | Mandatory CI #23 `080fd4b` | P0 | VERIFIED | run 38681816268 — PASS 5/5 |
| HANDOFF | Final engineering handoff | P0 | ACCEPTED | `docs/ops/FINAL_DELIVERY_HANDOFF.md` |

## Scores (frozen)

FULL **59** / MVP **56** / Design **15**. Staging criteria ○ until host GO + evidence. No score bump without criteria.

## Next (owner only)

1. Owner GO on Infrastructure C (or change A to ACK local-as-staging).
2. Then remote staging-up → E2E → score T10/T12.
3. Owner D02 / two-approver / SMTP / legal / pay partner / operator GOs from handoff §8.  
No further autonomous LOCAL engineering queue.
