# AUTONOMOUS_COMPLETION — очередь автономной разработки

Координатор: единая очередь, интеграция в `feat/master-plan-execution`, обновление PR #14.

| ID | Приоритет | Область | Задача | Агент | Файлы | Статус | Проверки | Commit | Blocker |
|----|-----------|---------|--------|-------|-------|--------|----------|--------|---------|
| AUTO-001 | P0 | docs | OWNER_INPUTS + AUTONOMOUS_STATE + .env.example | E | `docs/**`, `.env.example` | **DONE** | manual | `8f7b1ff` | — |
| AUTO-002 | P0 | frontend | Три маршрута кабинетов + redirect `/cabinet` | A | `apps/web/app/cabinet/**`, `lib/cabinetRoutes.ts` | **DONE** | web-lint, e2e | `3d88ac0` | — |
| AUTO-003 | P0 | frontend | Workspace switcher → правильный кабинет | A | `WorkspaceSwitcher.tsx` | **DONE** | web-lint | `3d88ac0` | — |
| AUTO-004 | P0 | backend | Payment adapter interface (fail-closed) | C | `apps/api/booker_api/payments/**` | **DONE** | test-api | `fbcc036` | — |
| AUTO-005 | P0 | backend | Notification adapters (disabled transport) | C | `apps/api/booker_api/notifications/**` | **DONE** | test-api | `38583f9` | — |
| AUTO-006 | P0 | backend | Race test двойного hold | D | `apps/api/tests/test_hold_race.py` | **DONE** | test-api | `fa2e7bb` | — |
| AUTO-007 | P0 | backend | OfferVersion/quote invariant tests | D | `apps/api/tests/test_quote_versioning.py` | **READY** | test-api | — | — |
| AUTO-008 | P0 | backend | Health/readiness feature flags | E | `routers/health.py`, `config.py` | **READY** | test-api | — | — |
| AUTO-009 | P1 | frontend | Customer dashboard shell (виджеты §7.5.3) | A | `cabinet/customer/**` | **READY** | e2e | — | AUTO-002 |
| AUTO-010 | P1 | frontend | Performer dashboard shell (§7.5.4) | A | `cabinet/performer/**` | **READY** | e2e | — | AUTO-002 |
| AUTO-011 | P1 | frontend | Venue dashboard shell + залы (§7.5.5) | A | `cabinet/venue/**` | **READY** | e2e | — | AUTO-002 |
| AUTO-012 | P1 | qa | Cross-role E2E полный цикл (§7.5.11) | D | `apps/web/e2e/cabinets-cross-role.spec.ts` | **READY** | e2e | — | AUTO-009–011 |
| AUTO-013 | P1 | frontend | Deal Room role-specific accents (§7.5.7) | A | `deals/[id]/**` | **READY** | e2e | — | — |
| AUTO-014 | P2 | frontend | a11y + reduced motion audit cabinets | A | `apps/web/**` | **READY** | e2e | — | AUTO-009 |
| AUTO-015 | P2 | ops | CI branch master→main fix | E | `.github/workflows/ci.yml` | **READY** | CI | — | — |
| AUTO-016 | — | legal | Юрпакет U5 | — | `docs/legal/**` | **EXTERNAL_BLOCKED** | — | — | OWNER_INPUTS |
| AUTO-017 | — | payments | Live payment partner | C | — | **EXTERNAL_BLOCKED** | — | — | AUTO-016 |

## Агенты

| Код | Роль | Ветки |
|-----|------|-------|
| Coordinator | очередь, интеграция, PR | `feat/master-plan-execution` |
| A | Frontend / UX | `agent/frontend-*` |
| B | Backend / domain | `agent/backend-*` |
| C | Security / payments | `agent/security-*` |
| D | Tests / QA | `agent/qa-*` |
| E | Infra / docs | `agent/ops-*` |

## Definition of Done (автономный цикл)

См. `docs/MASTER_PLAN.md` + §17 пользовательского промпта. PR #14 обновляется после каждой волны.
