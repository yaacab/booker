# TASK LEDGER — Букер critical path

Единая очередь исполнения. План: [ops/DELIVERY_PLAN_2026-10-15.md](ops/DELIVERY_PLAN_2026-10-15.md).
Измерение: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md).

Статусы: `NOT_STARTED` | `IMPLEMENTED` | `VERIFIED` | `BLOCKED` | `FAILED` | `ACCEPTED`

Обновлено: 2026-10-15 (master-completion wave). Кандидат: `bb61e998`. Ветка: `cursor/delivery-mvp-acceptance-cbf8`.

| ID | Задача | Pri | Status | Evidence / note |
|---|---|---|---|---|
| A0 | Bootstrap DELIVERY_PLAN + TASK_LEDGER | P0 | ACCEPTED | prior |
| A1–A3 | Stage A CI + review + ACCEPT | P0 | ACCEPTED | prior — do not redo |
| B1a | Remote staging host discovery | P0 | BLOCKED | No DNS/host; docker absent on agent — `ops/evidence/2026-10-15-staging-discovery.md` |
| B1b | Staging package (compose/env/scripts) | P0 | IMPLEMENTED | `infra/staging-*`, `env.staging.example`, Makefile — `ops/evidence/2026-10-15-staging-package.md` |
| B2a | LOCAL migrate+backup+restore rehearsal | P0 | VERIFIED | SQLite RTO 0.559s, rev `b12f34e56a78`, marker PASS — **not** T10 score |
| B2b | Schema manifest vs head (no stamp) | P0 | VERIFIED | head=`b12f34e56a78`; 40× manual_block preserved |
| C01–C03,C05–C07,C09–C10 | Prior local acceptance | P0 | VERIFIED | prior SCENARIOS — do not redo full suite |
| C04d | Deepen messaging roundtrip | P0 | VERIFIED | `test_acceptance_c04_c08.py` PASS LOCAL |
| C08d | Threaded hold exclusivity | P0 | VERIFIED | same file PASS LOCAL; PG staging race still open |
| S06a | Dual-admin offline recover deny + session revoke | P0 | VERIFIED | `test_staff_recovery.py` PASS LOCAL |
| S06b | Two-approver process / real SMTP | P0 | BLOCKED | owner packet |
| E1 | Pilot access docs | P1 | IMPLEMENTED | prior |
| F1 | GO/NO-GO production | P0 | ACCEPTED | **NO-GO** prior; re-issue after staging ACK |
| OWN1 | Owner approval packet | P0 | IMPLEMENTED | `ops/evidence/2026-10-15-owner-approval-packet.md` |

## Scores (unchanged)

FULL **59** / MVP **56** / Design **15**. T10/T12/P06/O05 remain ○ until staging ACK.

## Next (after owner)

1. ACK local-as-staging **or** remote URL.
2. `make staging-up` on a host with Docker → Postgres migrate → staging E2E.
3. Close T10/T12 only with staging-level evidence.

## Правила

1. Не объявлять VERIFIED/ACCEPTED только по зелёному CI без сценария, если сценарий в scope.
2. Не повышать проценты без критерия в `PROJECT_PROGRESS.md` и постоянного evidence.
3. Один исполнитель на файл; при конфликте — стоп конфликтующей операции.
4. Design / Club / referral / live payments — вне критического пути до закрытия staging gates.
