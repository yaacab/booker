# TASK LEDGER — Букер critical path

Единая очередь исполнения. План: [ops/DELIVERY_PLAN_2026-10-15.md](ops/DELIVERY_PLAN_2026-10-15.md).
Измерение: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md).

Статусы: `NOT_STARTED` | `IMPLEMENTED` | `VERIFIED` | `BLOCKED` | `FAILED` | `ACCEPTED`

Обновлено: 2026-10-15. Кандидат: `bb61e998`. Ветка: `cursor/delivery-mvp-acceptance-cbf8`.

| ID | Задача | Pri | Status | Evidence / note |
|---|---|---|---|---|
| A0 | Bootstrap DELIVERY_PLAN + TASK_LEDGER | P0 | ACCEPTED | `2e52169` + follow-up evidence commit |
| A1 | Stage A — CI 5/5 на `bb61e998` | P0 | VERIFIED | GitHub run 38480746776 SUCCESS |
| A2 | Stage A — review threads / blocking defects | P0 | VERIFIED | 0 threads; hold/quote/authz/support local PASS |
| A3 | Stage A — verdict ACCEPT/FIX_REQUIRED/BLOCKED | P0 | ACCEPTED | **ACCEPT** — `ops/evidence/2026-10-15-candidate-review.md` |
| B1 | Stage B — staging address/version/DB | P0 | BLOCKED | No staging DNS/host; prod only — `ops/evidence/2026-10-15-staging-discovery.md` |
| B2 | Stage B — migrations / roles / backup / rollback | P0 | BLOCKED | Depends on B1; local restore ≠ staging |
| C01 | Acceptance: создание события | P0 | VERIFIED | PASS локально — SCENARIOS.md |
| C02 | Acceptance: выбор артиста/площадки | P0 | VERIFIED | PASS локально |
| C03 | Acceptance: отправка заявки | P0 | VERIFIED | PASS локально (deal-path E07) |
| C04 | Acceptance: Deal Room + переписка | P0 | VERIFIED | PASS локально |
| C05 | Acceptance: предложение + quote_id цена | P0 | VERIFIED | PASS локально |
| C06 | Acceptance: подтверждение сторон | P0 | VERIFIED | PASS локально (E08) |
| C07 | Acceptance: создание бронирования | P0 | VERIFIED | PASS локально |
| C08 | Acceptance: запрет конфликтующей брони (+race) | P0 | VERIFIED | PASS локально (hold_race + E09) |
| C09 | Acceptance: поддержка + оператор | P0 | VERIFIED | PASS локально; SMTP/Telegram не заявлены |
| C10 | Acceptance: роли / права / изоляция | P0 | VERIFIED | PASS локально |
| D1 | Fix confirmed defects only | P0 | ACCEPTED | N/A — no FAIL — `ops/evidence/2026-10-15-stage-d.md` |
| E1 | Pilot roles / support duty / revoke | P1 | IMPLEMENTED | Documented; real users not granted — `ops/evidence/2026-10-15-pilot-access.md` |
| F1 | GO / NO-GO package | P0 | ACCEPTED | **NO-GO production** — `ops/evidence/2026-10-15-GO-NOGO.md` |

## Next critical path (after owner input)

1. Unblock B1/B2 with isolated staging facts.
2. Re-run C01–C10 at staging level → close T10/T12/P06/O05 only with evidence.
3. Re-issue F1.

## Правила

1. Не объявлять VERIFIED/ACCEPTED только по зелёному CI без сценария, если сценарий в scope.
2. Не повышать проценты без критерия в `PROJECT_PROGRESS.md` и постоянного evidence.
3. Один исполнитель на файл; при конфликте — стоп конфликтующей операции.
4. Design / Club / referral / live payments — вне критического пути до закрытия staging gates.
