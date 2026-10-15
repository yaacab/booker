# DELIVERY PLAN — 2026-10-15

Единый операционный план критического пути до проверенного технического MVP / контролируемого пилота.
Не заменяет продукт: [CONTRACT.md](../product/CONTRACT.md), измерение: [PROJECT_PROGRESS.md](../PROJECT_PROGRESS.md), очередь разработки: [DEVELOPMENT_GOAL.md](../DEVELOPMENT_GOAL.md).
Очередь задач: [TASK_LEDGER.md](../TASK_LEDGER.md).

## Кандидат

| Поле | Значение |
|---|---|
| SHA | `bb61e998f52b4eafd5a13efbb39567a57e7435d2` |
| Branch | `codex/booker-integrated-mvp-20261003` → рабочая `cursor/delivery-mvp-acceptance-cbf8` |
| PR | [#20](https://github.com/yaacab/booker/pull/20) (draft; merge только по OK владельца) |
| Base `master` | `ca20ac261b3cdc82e68c19d89a3150623109ebc0` (предок кандидата) |
| CI (5/5) | secret-source, dependency-audit, api, web, e2e-critical — SUCCESS на SHA кандидата |
| Предшествующий срез | [INTEGRATED_CANDIDATE_2026-10-03.md](INTEGRATED_CANDIDATE_2026-10-03.md), [INTEGRATION_REVIEW_MAP_2026-10-03.md](INTEGRATION_REVIEW_MAP_2026-10-03.md) |

`3fe9966` (упоминание обновлённых планов) в remote **не найден** — этот файл и `TASK_LEDGER.md` восстановлены 2026-10-15 как канон поверх существующего реестра прогресса.

## Готовность (не менять без критерия + evidence)

Источник: `docs/PROJECT_PROGRESS.md` на кандидате.

| Шкала | Баллы |
|---|---:|
| FULL | 59/100 |
| Technical MVP | 56/100 |
| Design | 15/100 |

Остаток FULL 41 п.п. закрывается только по исходным весам реестра. Локальный build / повтор CI / переписанный план — 0 п.п.

## Цикл

`DISCOVER → VERIFY → REUSE → COMPLETE → TEST → EVIDENCE → NEXT`

Запрещено возвращаться к DISCOVER без новой информации. Существующая реализация считается готовой, пока проверка не докажет обратное.

## Этапы

| ID | Этап | Цель | Статус (см. ledger) |
|---|---|---|---|
| A | Review кандидата | ACCEPT / FIX_REQUIRED / BLOCKED на `bb61e998` | **ACCEPT** |
| B | Staging discovery | Адрес, версия, БД, миграции, роли, backup/rollback; без recreate | **BLOCKED** (нет отдельного staging) |
| C | Сквозная приёмка | 10 обязательных сценариев с evidence | **VERIFIED** локально |
| D | Дефекты | Только воспроизводимые FAIL; минимальный diff | **N/A** (нет FAIL) |
| E | Пилотный доступ | Роли, поддержка, правила ограниченного пилота — без реального GO | **IMPLEMENTED** (без реальных users) |
| F | Release readiness | Пакет GO / NO-GO; **не** production deploy | **NO-GO** production |

## Запреты без отдельного согласования

Production / DNS / платежи / реальные бронирования / destructive migrations / `git reset --hard` / force push / массовый рефакторинг / redesign / Club / referral / скидки.

Классификация действий: READ-ONLY → SAFE LOCAL → STAGING MUTATION (только изолированная среда) → PRODUCTION (стоп + запрос).

## Evidence

Канон: `docs/ops/evidence/`. Не хранить единственную копию в `/tmp`. Секреты и ПДн в отчёты не писать.

## Rollback target (кандидат)

- App rollback: предыдущий known-good SHA на `master` = `ca20ac2` (до интеграции PR #20).
- Schema: manifest остаётся `manual_block` до staging restore proof.
- Production deploy запрещён до явного GO владельца.
