# AUTONOMOUS_STATE — координатор автономной разработки

**Обновлено:** 2026-09-01  
**Ветка:** `feat/master-plan-execution`  
**HEAD:** _(после push AUTO-014)_
  
**PR:** https://github.com/yaacab/booker/pull/14

## Текущая фаза

Волна 4 завершена (014–015). Все P0–P2 технические задачи **DONE**. Остаются только EXTERNAL_BLOCKED (016–017).

## Следующая задача

Нет автономных READY-задач. Ожидание OWNER_INPUTS для AUTO-016 (юрпакет).

## Последние проверки

| Команда | Результат | Когда |
|---------|-----------|-------|
| `make test-api` | ok | 2026-09-01 |
| `make web-lint` | ok | 2026-09-01 |
| `make web-build` | ok | 2026-09-01 |
| `npm run test:unit` | 15 passed | 2026-09-01 |
| E2E (flow + cross-role + a11y) | 15 passed, 4 skipped | 2026-09-01 |

## Решения

- `design-qa.md` в репозитории отсутствует — опираемся на CONTRACT + BLUEPRINT + MASTER_PLAN.
- Org kind API: `customer` | `artist` | `venue`; UI маршрут исполнителя: `/cabinet/performer` (alias для `artist`).
- `/health` и `/readiness` отражают feature flags, notification providers и missing OWNER_INPUTS для включённых возможностей.
- `/readiness` → 503 только при недоступной БД или незаполненных OWNER_INPUTS для запрошенных live-фич.
- Ack оффера отклоняет устаревший `quote_id` (409) — подтверждается только активная OfferVersion.
- Performer cabinet: виджеты новые заявки / ожидающие ответа / истекающие предложения / hold / ближайшие выступления / конфликты календаря / completeness + Supply-секция (услуги, iCal, vacation).
- Venue cabinet: те же supply-виджеты + залы (calendar-targets) + Supply-секция.
- Cross-role E2E: demo seed `customer@booker.test`, `artist@booker.test`, `venue@booker.test`; venue user добавлен в seed; `list_requests` резолвит hall-слоты для `resource_type=venue`.
- Deal Room accents: `workspace_kind` в `/deal-room/{id}`; UI-сетка акцентов customer/performer/venue на вкладке «Сводка»; booking_id и quote_id едины для всех ролей.
- event-studio-map v1 (4 теста с `?event_studio_map_v1=1`): skip — UI hidden, не регрессия cabinet.
- Cabinet a11y: `CabinetPageShell` (landmarks, skip-to-widgets, skeleton status); `DashboardWidget` с `aria-labelledby`; reduced-motion сброс hover-transform; e2e `cabinet-a11y.spec.ts`.
- Seed `_ensure_cross_role_catalog`: replenishes open slots в горизонте 30д для DJ Nova и Клуб Сигнал после исчерпания demo-слотов.
- CI: `.github/workflows/ci.yml` триггерит `main` (AUTO-015 уже выполнен).

## Handoff

При исчерпании контекста: прочитать этот файл + `docs/AUTONOMOUS_COMPLETION.md`. Автономная очередь P0–P2 исчерпана — ждём OWNER_INPUTS для юрпакета и live payments.
