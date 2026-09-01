# AUTONOMOUS_STATE — координатор автономной разработки

**Обновлено:** 2026-09-01  
**Ветка:** `feat/master-plan-execution`  
**HEAD:** `ac8a026`
  
**PR:** https://github.com/yaacab/booker/pull/14

## Текущая фаза

Волна 2 завершена (012). Следующая: Deal Room accents (013).

## Следующая задача

`AUTO-013` Deal Room role-specific accents (§7.5.7, P1).

## Последние проверки

| Команда | Результат | Когда |
|---------|-----------|-------|
| `make test-api` | 131 passed, 2 skipped | 2026-09-01 |
| `make web-lint` | ok | 2026-09-01 |
| `make web-build` | ok | 2026-09-01 |
| E2E | 13 passed, 4 skipped | 2026-09-01 |

## Решения

- `design-qa.md` в репозитории отсутствует — опираемся на CONTRACT + BLUEPRINT + MASTER_PLAN.
- Org kind API: `customer` | `artist` | `venue`; UI маршрут исполнителя: `/cabinet/performer` (alias для `artist`).
- `/health` и `/readiness` отражают feature flags, notification providers и missing OWNER_INPUTS для включённых возможностей.
- `/readiness` → 503 только при недоступной БД или незаполненных OWNER_INPUTS для запрошенных live-фич.
- Ack оффера отклоняет устаревший `quote_id` (409) — подтверждается только активная OfferVersion.
- Performer cabinet: виджеты новые заявки / ожидающие ответа / истекающие предложения / hold / ближайшие выступления / конфликты календаря / completeness + Supply-секция (услуги, iCal, vacation).
- Venue cabinet: те же supply-виджеты + залы (calendar-targets) + Supply-секция.
- Cross-role E2E: demo seed `customer@booker.test`, `artist@booker.test`, `venue@booker.test`; venue user добавлен в seed; `list_requests` резолвит hall-слоты для `resource_type=venue`.
- event-studio-map v1 (4 теста с `?event_studio_map_v1=1`): skip — UI hidden, не регрессия cabinet.

## Handoff

При исчерпании контекста: прочитать этот файл + `docs/AUTONOMOUS_COMPLETION.md`, продолжить с `Следующая задача`.
