# Production data layer — план P0

Источник: MASTER_PLAN `p0-prod-infra`. Юридический контекст: [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md).

## Текущее состояние (пилот 2026-08)

| Компонент | Сейчас | Целевое P0 |
|-----------|--------|------------|
| API | VPS `5.45.112.180`, systemd `booker-api` | то же |
| Web | nginx + `booker-web` (Next.js) | то же |
| БД | SQLite `/opt/booker/data/booker.db` | Managed Postgres 16 в РФ |
| Redis | нет | Managed Redis (сессии/rate limit при горизонтальном API) |
| Object storage | нет (файлы не принимаем) | Yandex Object Storage при появлении upload |
| Backups | **не автоматизированы** | daily + retention 30d |
| Restore drill | **не проведён** | quarterly, документировать RTO |

`BOOKER_DATABASE_URL` в [config.py](../../apps/api/booker_api/config.py); локальный Postgres: `infra/docker-compose.yml`.

## Фаза 1 — бэкапы SQLite (до миграции)

1. Cron на VPS (пример `02:15` UTC+3):

```bash
# /etc/cron.d/booker-backup
15 2 * * * root /opt/booker/infra/backup-booker.sh >> /var/log/booker-backup.log 2>&1
```

2. Скрипт: [infra/backup-booker.sh](../../infra/backup-booker.sh) — `sqlite3 .backup` + gzip, retention 30 дней.
3. Копия off-site: rsync bucket/S3 в том же облаке РФ (ручной шаг до выбора провайдера).

## Фаза 2 — Postgres

### Подготовка

```bash
# локально
docker compose -f infra/docker-compose.yml up -d postgres
export BOOKER_DATABASE_URL=postgresql+psycopg://booker:booker@127.0.0.1:5432/booker
cd apps/api && python -m booker_api.seed
make test-api
```

Драйвер: добавить `psycopg[binary]` в `apps/api/pyproject.toml` при первой миграции.

### Прод cutover (окно обслуживания)

1. `systemctl stop booker-api booker-web`
2. `pg_dump` / импорт из SQLite (одноразовый скрипт миграции — TODO при cutover)
3. `BOOKER_DATABASE_URL=postgresql+psycopg://...` в `/etc/systemd/system/booker-api.service`
4. `systemctl start booker-api` → `/health` → smoke E2E
5. Первый `backup-booker.sh` для Postgres

### Alembic

Baseline: `apps/api/alembic/versions/*_baseline.py` — все ORM-таблицы из [models.py](../../apps/api/booker_api/models.py).

```bash
docker compose -f infra/docker-compose.yml up -d postgres
export BOOKER_DATABASE_URL=postgresql+psycopg://booker:booker@127.0.0.1:5432/booker
make migrate
cd apps/api && python -m booker_api.seed
make test-api
```

На Postgres API при старте вызывает `alembic upgrade head` ([db.py](../../apps/api/booker_api/db.py)). SQLite (локальные тесты) — по-прежнему `create_all` + `ensure_missing_columns`.

## Restore drill (чеклист)

| Шаг | Действие | Ожидание |
|-----|----------|----------|
| 1 | Выбрать backup не старше 24h | файл `.gz` в `/var/backups/booker/` |
| 2 | Staging VM или `/opt/booker-restore-test` | изолированный путь |
| 3 | Restore DB из backup | `sqlite3` или `pg_restore` |
| 4 | `BOOKER_DATABASE_URL` → restored | API стартует |
| 5 | `curl /health` + `make test-api` на staging | зелёные |
| 6 | Записать RTO, проблемы | строка в журнале MASTER_PLAN |

Целевой RTO пилота: **< 4 ч** (ручной restore на VPS).

## Аудит хостинга РФ (152-ФЗ)

| Проверка | Статус | Действие |
|----------|--------|----------|
| VPS в РФ | ✓ Selectel/Yandex IP в РФ | зафиксировать в OPERATOR.md |
| БД ПДн в РФ | ✓ SQLite на VPS | Postgres — same region |
| Логи/бэкапы в РФ | partial | off-site backup в РФ |
| Sentry/аналитика | audit | нет трансграничной передачи ПДн |
| Уведомление РКН | BLOCKED | см. p0-legal-289 |
| SSL bukergo.ru | ✓ | [DOMAINS.md](DOMAINS.md) |

## Не в scope этого плана

- Kubernetes / multi-region
- Live payment rails (U5)
- File upload + AV scan

## Статус выполнения

- [x] План и скрипт бэкапа
- [ ] Cron на прод VPS
- [ ] Первый успешный backup + verify
- [ ] Restore drill (staging)
- [ ] Postgres cutover
- [x] Alembic baseline
