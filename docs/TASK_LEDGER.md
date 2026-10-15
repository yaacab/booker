# TASK LEDGER — Букер critical path

Единая очередь исполнения. План: [ops/DELIVERY_PLAN_2026-10-15.md](ops/DELIVERY_PLAN_2026-10-15.md).
Измерение: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md).

Статусы: `NOT_STARTED` | `IMPLEMENTED` | `VERIFIED` | `BLOCKED` | `FAILED` | `ACCEPTED`

Обновлено: 2026-10-15. Кандидат: `bb61e998`. Ветка: `cursor/delivery-mvp-acceptance-cbf8`.

| ID | Задача | Pri | Status | Evidence / note |
|---|---|---|---|---|
| A0 | Bootstrap DELIVERY_PLAN + TASK_LEDGER | P0 | IMPLEMENTED | docs created; awaiting commit |
| A1 | Stage A — CI 5/5 на `bb61e998` | P0 | VERIFIED | GitHub run 38480746776 SUCCESS |
| A2 | Stage A — review threads / blocking defects | P0 | NOT_STARTED | PR #20: 0 reviews at discovery |
| A3 | Stage A — verdict ACCEPT/FIX_REQUIRED/BLOCKED | P0 | NOT_STARTED | — |
| B1 | Stage B — staging address/version/DB | P0 | NOT_STARTED | READ-ONLY discovery |
| B2 | Stage B — migrations / roles / backup / rollback | P0 | NOT_STARTED | — |
| C01 | Acceptance: создание события | P0 | NOT_STARTED | reuse flow/deal-path e2e |
| C02 | Acceptance: выбор артиста/площадки | P0 | NOT_STARTED | search + catalog |
| C03 | Acceptance: отправка заявки | P0 | NOT_STARTED | deal-path |
| C04 | Acceptance: Deal Room + переписка | P0 | NOT_STARTED | deal-path / messages |
| C05 | Acceptance: предложение + quote_id цена | P0 | NOT_STARTED | quote_versioning |
| C06 | Acceptance: подтверждение сторон | P0 | NOT_STARTED | deal-path / contract ack |
| C07 | Acceptance: создание бронирования | P0 | NOT_STARTED | holds |
| C08 | Acceptance: запрет конфликтующей брони (+race) | P0 | NOT_STARTED | test_hold_race.py |
| C09 | Acceptance: поддержка + оператор | P0 | NOT_STARTED | support e2e / admin queue |
| C10 | Acceptance: роли / права / изоляция | P0 | NOT_STARTED | authz + org-switch |
| D1 | Fix confirmed defects only | P0 | NOT_STARTED | after C |
| E1 | Pilot roles / support duty / revoke | P1 | NOT_STARTED | no real users until GO |
| F1 | GO / NO-GO package | P0 | NOT_STARTED | no production deploy |

## Правила

1. Не объявлять VERIFIED/ACCEPTED только по зелёному CI без сценария, если сценарий в scope.
2. Не повышать проценты без критерия в `PROJECT_PROGRESS.md` и постоянного evidence.
3. Один исполнитель на файл; при конфликте — стоп конфликтующей операции.
4. Design / Club / referral / live payments — вне критического пути до закрытия staging gates.
