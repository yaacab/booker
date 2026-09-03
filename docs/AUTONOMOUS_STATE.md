# AUTONOMOUS_STATE — координатор автономной разработки

**Обновлено:** 2026-09-01  
**Ветка:** `feat/master-plan-execution`  
**HEAD:** `a25f496` (2026-09-01 08:44:54 +0300; CI green)

**PR:** https://github.com/yaacab/booker/pull/14  
**CI:** https://github.com/yaacab/booker/actions/runs/33474795762 — **green** (`api` + `web`)

## Текущая фаза

**launch-readiness complete** + **Moscow open venues import** (`data/moscow_venues_open.json`, synthetic 30d slots).

## Следующая задача

OWNER_INPUTS AUTO-016/017; outreach площадок (`VENUE_OUTREACH_CONTACT`) для перевода на `availability_mode=owner`.

## Agent loop (launch audit)

**Остановлен** (audit complete, CI green на `a25f496`).

## Последние проверки

| Команда | Результат | Когда |
|---------|-----------|-------|
| `make web-lint` | ok | 2026-09-01 |
| `make lint` | ok | 2026-09-01 |
| `make test-api` | **131 passed**, 2 skipped | 2026-09-01 |
| `make web-build` | ok | 2026-09-01 |
| `npm run test:unit` | 15 passed | 2026-09-01 |
| E2E (`npm run test:e2e`) | **19 passed**, 0 skipped | 2026-09-01 |
| Event Studio Map E2E | **5/5 passed** (0 skip) | 2026-09-01 |
| Backup/restore drill | **OK (smoke)** — `infra/restore-drill.sh` с Python fallback (без `sqlite3` CLI) | 2026-09-01 |
| Postgres migrate + subset | **OK (docker)** — `make migrate-docker` / `./infra/migrate-postgres-docker.sh` → alembic head | 2026-09-01 |
| CI PR #14 (`api` + `web`) | **green** (`a25f496`) | 2026-09-01 |

## Решения (launch audit)

- **Event Studio Map skips fixed:** React переиспользовал DOM `#scroll-progress` как `#content` при переключении `fullScreenStudio`; inline `transform: scaleX(0)` схлопывал UI (Playwright: hidden, width 0). Fix в `SiteChrome.tsx`: sync init флага, `key` на fullscreen root, scroll handler только вне fullscreen, `.studio-fullscreen-root { transform: none !important }`.
- **design-qa.md** — актуален в корне репо; screenshots обновлены в `docs/screenshots/event-studio-map-v1/`.
- **Cross-role E2E flake:** retry слотов при 409 + randomised slot window в `e2e/helpers.ts`.
- **Mobile map E2E:** закрытие bottom sheet через `Закрыть панель` (backdrop под sheet).

## Ops (a25f496)

- **restore-drill:** Python fallback в `infra/restore-drill.sh` когда `sqlite3` CLI отсутствует.
- **Postgres migrate:** `make migrate-docker` / `infra/migrate-postgres-docker.sh` для локального alembic без рабочего host Python.

## Env notes

- `sqlite3` CLI **опционален** — restore-drill smoke работает через Python; 2 pytest backup-теста skip локально без CLI.
- Host `make migrate` **заблокирован** (`_ctypes` в pyenv 3.11.6) — использовать **`make migrate-docker`**.

## EXTERNAL_BLOCKED (без изменений)

- AUTO-016 / AUTO-017 — OWNER_INPUTS (юрпакет U5, live payments).
- ClamAV — prod object storage sidecar.
- Postgres cutover prod — ops runtime.

## Следующий шаг

1. **OWNER_INPUTS:** AUTO-016 (юрпакет U5), AUTO-017 (live payments).
2. **PR #14** — review / merge владельцем (не merge автономно).
