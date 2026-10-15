# TASK LEDGER — Букер critical path

Единая очередь исполнения. План: [ops/DELIVERY_PLAN_2026-10-15.md](ops/DELIVERY_PLAN_2026-10-15.md).
Измерение: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md).

Статусы: `NOT_STARTED` | `IMPLEMENTED` | `VERIFIED` | `BLOCKED` | `FAILED` | `ACCEPTED`

Обновлено: 2026-10-15 (staging harden wave). Кандидат: `bb61e998`. Ветка: `cursor/delivery-mvp-acceptance-cbf8`.

| ID | Задача | Pri | Status | Evidence / note |
|---|---|---|---|---|
| A0–A3 | Stage A | P0 | ACCEPTED | prior — do not redo |
| B1a | Remote staging discovery | P0 | BLOCKED | DNS empty; owner B unused |
| B1b | Staging package | P0 | IMPLEMENTED | hardened — `2026-10-15-staging-hardened.md` |
| B1c | Fail-closed preflight + neg tests | P0 | VERIFIED | 13 PASS `infra/test_staging_preflight.py` |
| B1d | Host proposal (option C) | P0 | IMPLEMENTED | `2026-10-15-staging-host-proposal.md` — wait GO |
| B2a | LOCAL SQLite rehearsal | P0 | VERIFIED | prior — do not redo |
| C01–C10 | Local acceptance | P0 | VERIFIED | prior; C04/C08 deepened prior |
| S06a | Dual-admin recover deny | P0 | VERIFIED | prior local |
| S06b | Two-approver / SMTP / staging proof | P0 | BLOCKED | owner |
| T09a | Catalog pagination local tests | P1 | VERIFIED | 10 PASS LOCAL — score still ○ |
| T11a | Authz/privacy + fake AV local | P1 | VERIFIED | 43+11 PASS LOCAL — score still ○ |
| T13a | Ops prep / runbook for future host | P1 | IMPLEMENTED | LOCAL prep only |
| OWN1 | Owner packet | P0 | ACCEPTED | A/B/C recorded; wait C GO |
| F1 | Production GO/NO-GO | P0 | ACCEPTED | **NO-GO** |

## Scores (frozen)

FULL **59** / MVP **56** / Design **15**. Staging criteria ○ until host GO + evidence.

## Next

1. Owner GO on option C (or change A to ACK local-as-staging).
2. Then remote/local docker staging-up → E2E → score T10/T12.
