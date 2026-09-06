# Postgres staging proof (diligence Wave E)

Цель: показать, что cutover **подготовлен**, без обязательного prod-switch (CONTRACT: SQLite ок для малого concierge).

## Прогон 2026-09-06

| Шаг | Команда | Результат |
|-----|---------|-----------|
| 1. Postgres 16 | `docker-compose -f infra/docker-compose.yml up -d postgres` | PASS — `127.0.0.1:5432` |
| 2. Alembic head | `make migrate-docker` (`postgresql+psycopg://booker:booker@127.0.0.1:5432/booker`) | PASS — upgrades через `d4e8b2a9c1f0` (password_reset_tokens) |
| 3. Unit API | `make test-api` на SQLite (дефолт CI) | PASS — 151+ |
| 4. Prod cutover | — | **не выполнялся** (go/no-go отдельно, см. `PROD_INFRA.md`) |

## Как повторить

```bash
docker-compose -f infra/docker-compose.yml up -d postgres
make migrate-docker
# опционально полный pytest в контейнере после чистого volume:
# docker-compose -f infra/docker-compose.yml down -v
# docker-compose -f infra/docker-compose.yml up -d postgres && make migrate-docker
```

Runbook prod: [PROD_INFRA.md](PROD_INFRA.md) § Postgres cutover.
