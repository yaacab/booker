# AUTONOMOUS_STATE — координатор автономной разработки

**Обновлено:** 2026-09-01  
**Ветка:** `feat/master-plan-execution`  
**HEAD:** `251bdd9` (локально; CI зелёный на том же коммите)

**PR:** https://github.com/yaacab/booker/pull/14

## Текущая фаза

**launch-readiness follow-up (tick 1)** — env gates документированы; restore-drill smoke через Python fallback; Postgres migrate через Docker wrapper.

## Agent loop (launch audit)

**Остановлен** (PID 205543, audit complete, CI green).

## Последние проверки (launch audit tick 0)

| Команда | Результат | Когда |
|---------|-----------|-------|
| `make web-lint` | ok | 2026-09-01 |
| `make lint` | ok | 2026-09-01 |
| `make test-api` | 131 passed, 2 skipped | 2026-09-01 |
| `make web-build` | ok | 2026-09-01 |
| `npm run test:unit` | 15 passed | 2026-09-01 |
| E2E (`npm run test:e2e`) | **19 passed**, 0 skipped | 2026-09-01 |
| Event Studio Map E2E | **5/5 passed** (0 skip) | 2026-09-01 |
| Backup/restore drill | **OK (smoke)** — `infra/restore-drill.sh` с Python fallback (без `sqlite3` CLI); полные pytest backup-тесты всё ещё skip без CLI | 2026-09-01 |
| Postgres migrate + subset | **OK (docker)** — `infra-postgres-1` up; `make migrate` fail (`_ctypes` в pyenv 3.11.6); **`make migrate-docker`** / `./infra/migrate-postgres-docker.sh` → alembic head | 2026-09-01 |
| CI PR #14 (`api` + `web`) | **green** (`251bdd9`) | 2026-09-01 |

## Решения (launch audit)

- **Event Studio Map skip root cause:** React переиспользовал DOM `#scroll-progress` как `#content` при переключении `fullScreenStudio`; inline `transform: scaleX(0)` схлопывал UI (Playwright: hidden, width 0). Fix: sync init флага, `key` на fullscreen root, scroll handler только вне fullscreen, `.studio-fullscreen-root { transform: none !important }`.
- **design-qa.md** — актуален в корне репо; screenshots обновлены в `docs/screenshots/event-studio-map-v1/`.
- **Cross-role E2E flake:** retry слотов при 409 + randomised slot window в `e2e/helpers.ts`.
- **Mobile map E2E:** закрытие bottom sheet через `Закрыть панель` (backdrop под sheet).

## EXTERNAL_BLOCKED (без изменений)

- AUTO-016 / AUTO-017 — OWNER_INPUTS (юрпакет U5, live payments).
- Postgres cutover prod — ops runtime; локально migrate заблокирован `_ctypes` в pyenv Python.

## Handoff

Launch-readiness: merges не в `master`. Ops: `sudo dnf install -y sqlite3` (или PATH к CLI) для полного backup pytest; пересборка pyenv Python с libffi для `make migrate`, либо `make migrate-docker` локально.
