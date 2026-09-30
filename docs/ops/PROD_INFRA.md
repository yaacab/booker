# Production data layer — P0

Источник: MASTER_PLAN `p0-prod-infra`. Юридический контекст: [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md).

Скрипты и чеклисты подготовлены, но восстановимость считается подтверждённой только после отдельного staging-drill на свежем архиве. Остаётся **ops/runtime** — выполнение пунктов в разделе «Runtime (только прод)».

## Текущее состояние (пилот 2026-09)

| Компонент | Сейчас | Целевое P0 |
|-----------|--------|------------|
| API | VPS `5.45.112.180`, systemd `booker-api` | то же |
| Web | nginx + `booker-web` (Next.js) | то же |
| БД | SQLite `/opt/booker/data/booker.db` | Managed Postgres 16 в РФ |
| Redis | нет | Managed Redis (сессии/rate limit при горизонтальном API) |
| Object storage | нет (файлы не принимаем) | Yandex Object Storage при появлении upload |
| Backups | versioned tar.gz + manifest/SHA-256 | daily + retention 30d + off-site, **verify на staging** |
| Restore drill | скрипт + pytest smoke | quarterly на staging, документировать RTO |
| Alembic | baseline `a44d171` | `alembic upgrade head` на Postgres |

`BOOKER_DATABASE_URL` в [config.py](../../apps/api/booker_api/config.py); локальный Postgres: `infra/docker-compose.yml`.

---

## Runtime (только прод) — что осталось

Код не заменяет runtime-проверку. Выполнить на VPS / в облаке РФ:

- [ ] **Cron verify** — после `make deploy`: `cat /etc/cron.d/booker-backup`, дождаться 02:15 MSK или запустить вручную `BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db /opt/booker/infra/backup-booker.sh`
- [ ] **Первый backup + verify** — `booker-*.tar.gz` и соседний `.sha256`; проверить sidecar и выполнить restore drill на staging (см. ниже)
- [ ] **Restore drill (staging)** — пройти чеклист «Restore drill», записать RTO в журнал MASTER_PLAN
- [ ] **Postgres cutover** — пройти чеклист «Postgres cutover» в окне обслуживания
- [ ] **RU hosting audit** — пройти чеклист «Аудит хостинга РФ», зафиксировать evidence

---

## Фаза 1 — бэкапы SQLite (до миграции)

Deploy ([infra/deploy-vps.sh](../../infra/deploy-vps.sh)) создаёт `/var/backups/booker`, ставит cron из [cron-booker-backup.example](../../infra/cron-booker-backup.example), запускает первый backup (non-fatal).

Ручная установка cron (если deploy не использовался):

```bash
sudo cp /opt/booker/infra/cron-booker-backup.example /etc/cron.d/booker-backup
sudo chmod 644 /etc/cron.d/booker-backup
```

Скрипт: [infra/backup-booker.sh](../../infra/backup-booker.sh). Он берёт эксклюзивную lock, делает online snapshot SQLite через стандартный Python `sqlite3.backup()` или PostgreSQL custom dump и metadata из одного `pg_export_snapshot`, копирует `uploads/`, пишет manifest и только затем атомарно публикует архив. Retention по умолчанию — 30 дней.

Формат новых архивов (v2):

| БД | Имя архива | Payload внутри | Восстановление |
|----|-------------|----------------|----------------|
| SQLite | `booker-YYYYMMDDTHHMMSSZ.tar.gz` | `booker.db`, `uploads/`, `manifest.json` | `restore-drill.sh` в новый каталог |
| PostgreSQL | `booker-pg-YYYYMMDDTHHMMSSZ.tar.gz` | custom-format `booker.dump`, `uploads/`, `manifest.json` | `restore-drill.sh` в заранее созданную пустую staging-БД |

`manifest.json` содержит SHA-256 БД и каждого файла uploads, состав и отпечаток схемы, состояние Alembic и количества строк ключевых таблиц. Рядом создаётся `<archive>.sha256` для проверки всего tar.gz. Sidecar нужно копировать off-site вместе с архивом: v2 drill без него завершается ошибкой, потому что иначе сам manifest не защищён внешней контрольной суммой. Старые tar.gz с `booker.db` или `booker.dump` остаются читаемыми; drill помечает их как `legacy`. Выполнение старого plain-SQL dump дополнительно требует `BOOKER_RESTORE_ALLOW_LEGACY_PLAIN_SQL=trusted-archive`.

Каталог uploads обязателен. Если в установке заведомо ещё нет файлового хранилища, пустой набор разрешается только явно: `BOOKER_ALLOW_MISSING_UPLOAD_DIR=1`. Символические ссылки и специальные файлы в uploads приводят к ошибке.

```bash
# ручной SQLite backup
BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db \
BOOKER_UPLOAD_DIR=/opt/booker/data/uploads \
/opt/booker/infra/backup-booker.sh

# проверка архива целиком; выполнять из каталога backup
cd /var/backups/booker
sha256sum -c booker-YYYYMMDDTHHMMSSZ.tar.gz.sha256
```

Snapshot БД консистентен сам по себе; PostgreSQL dump, schema/Alembic metadata и row counts используют один exported snapshot. БД и локальный `uploads/` всё равно снимаются последовательно. Если приложение уже принимает вложения, на время backup нужно остановить запись файлов либо использовать согласованный filesystem/object-storage snapshot. Обычный запуск скрипта не доказывает межресурсную point-in-time консистентность.

Off-site копия (ручной шаг до выбора bucket):

```bash
# пример: rsync в bucket/S3 того же облака РФ
rsync -az /var/backups/booker/ user@backup-host:/backups/booker/
```

---

## Аудит хостинга РФ (152-ФЗ) — чеклист

**Цель:** подтвердить, что ПДн и инфраструктура обработки остаются в РФ до публичного сбора. Юридические гейты — [OPERATOR.md](../legal/OPERATOR.md), [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md).

| # | Проверка | Как проверить | Pass-критерий | Evidence (куда записать) |
|---|----------|---------------|---------------|--------------------------|
| A1 | VPS / compute в РФ | `whois 5.45.112.180`, договор с хостером | IP и дата-центр в РФ (Selectel / Yandex / аналог) | строка в OPERATOR.md или этот файл, дата аудита |
| A2 | DNS и TLS | `dig +short bukergo.ru A`, `curl -sI https://bukergo.ru` | A → prod VPS, валидный HTTPS | [DOMAINS.md](DOMAINS.md) |
| A3 | БД ПДн в РФ | путь `/opt/booker/data/booker.db` на VPS; после cutover — region managed Postgres | primary DB только в РФ, same region что API | cutover journal |
| A4 | Бэкапы в РФ | `ls /var/backups/booker`, off-site destination | копии не покидают РФ | bucket/хост off-site в том же облаке РФ |
| A5 | Логи приложения | `journalctl -u booker-api -n 5`, nginx access/error | логи на диске VPS в РФ | — |
| A6 | Sentry / внешняя аналитика | `.env` / systemd unit: нет DSN с трансграничной передачей ПДн | нет email/phone/name в third-party без DPA; или Sentry EU/RU / выключен | список env vars в audit note |
| A7 | CDN / fonts / статика | `grep -r cdn\\|googleapis apps/web` | только публичные ассеты, без ПДн в query | code review note |
| A8 | Object storage (когда появится) | bucket region | Yandex Object Storage / Selectel S3, region RU | PROD_INFRA journal |
| A9 | Уведомление РКН | статус p0-legal-289 | **EXTERNAL_BLOCKED** до реквизитов оператора | OPERATOR.md |
| A10 | Регламент инцидента ПДн | документ + ответственный | 24h / 72h по [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md) | legal pack |

**Подпись аудита (заполнить при прохождении на проде):**

```
Дата: __________  Ответственный: __________
A1–A8: pass / fail / n/a (по строкам)
Замечания: __________
```

---

## Postgres cutover — чеклист

**Pre-flight (за 1–3 дня до окна)**

- [ ] Managed Postgres 16 в том же облаке/регионе, что VPS (Yandex / Selectel)
- [ ] Создана БД `booker`, пользователь с минимальными правами, SSL enforced
- [ ] Секрет `BOOKER_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/booker?sslmode=require` — только в `/etc/systemd/system/booker-api.service`, не в git
- [ ] Локально: `docker compose -f infra/docker-compose.yml up -d postgres`, `make migrate`, `make test-api` — зелёные
- [ ] Smoke на staging Postgres: seed + `curl /health` + выборочные API
- [ ] Свежий SQLite backup: `backup-booker.sh`, файл сохранён off-site
- [ ] Окно обслуживания согласовано (ориентир: 30–60 мин), rollback plan понятен

**Подготовка миграции данных (одноразово)**

Предпочтительный порядок (избегает `relation already exists` на baseline):

1. Пустой Postgres → `alembic upgrade head` (создаёт схему + `alembic_version`)
2. Затем перенос данных **в уже существующие таблицы** (pgloader с `--with "including only table names …"` / data-only, или ручной import)
3. Сверить row counts

```bash
# на VPS, после stop API
export SRC=sqlite:////opt/booker/data/booker.db
export DST=postgresql+psycopg://USER:PASS@HOST:5432/booker

# 1) схема сначала
BOOKER_DATABASE_URL="${DST}" alembic -c apps/api/alembic.ini upgrade head

# 2) данные во существующие таблицы (не create schema заново)
# пример: pgloader data-only / согласованный скрипт — не вызывать create_table baseline повторно

# альтернатива для пилота: seed на пустой Postgres + ручной перенос критичных таблиц
```

Если таблицы уже залиты pgloader **без** `alembic_version` (legacy path): **не** запускать `upgrade` baseline. Вместо этого stamp текущей головы схемы и догнать только последующие ревизии:

```bash
# только если schema уже совпадает с baseline+промежуточными — иначе сверить колонки вручную
BOOKER_DATABASE_URL="${DST}" alembic -c apps/api/alembic.ini stamp ad7ec0cd0ee2
BOOKER_DATABASE_URL="${DST}" alembic -c apps/api/alembic.ini upgrade head
```

- [ ] Row counts сверены: `users`, `organizations`, `events`, `bookings`, `payments` (±0 или документированный delta)
- [ ] FK / unique constraints без ошибок в логе миграции
- [ ] `alembic_version` = head (`c7a9f0e1d2b3` или актуальный) **до** старта API

**Cutover (окно обслуживания)**

| # | Действие | Команда / проверка |
|---|----------|-------------------|
| C1 | Maintenance page (опционально) | nginx return 503 или статическая заглушка |
| C2 | Stop services | `systemctl stop booker-web booker-api` |
| C3 | Final SQLite backup | `BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db /opt/booker/infra/backup-booker.sh` |
| C4 | Schema + data | Пустой PG → `alembic upgrade head` → data load (см. выше); **не** `upgrade` поверх сырого pgloader-schema без stamp |
| C5 | Alembic verify | `alembic current` = head; при stamp-path — только post-baseline ревизии |
| C6 | Update systemd | `Environment=BOOKER_DATABASE_URL=postgresql+psycopg://...` в `booker-api.service` |
| C7 | Start API | `systemctl daemon-reload && systemctl start booker-api` |
| C8 | Health | `curl -sS http://127.0.0.1:8030/health` → 200 |
| C9 | Smoke web | `curl -sI https://bukergo.ru`, login test account |
| C10 | Start web | `systemctl start booker-web` |
| C11 | E2E / manual flow | login → deal room → cabinet (см. `apps/web/e2e/flow.spec.ts`) |
| C12 | Postgres backup | `BOOKER_DATABASE_URL=postgresql+... /opt/booker/infra/backup-booker.sh` |
| C13 | Monitor 24h | `journalctl -u booker-api -f`, latency, 5xx |

**Rollback (если C8–C11 fail)**

1. `systemctl stop booker-api booker-web`
2. Вернуть `BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db` в systemd
3. При необходимости восстановить SQLite из backup C3
4. `systemctl start booker-api booker-web`
5. Записать incident + причину в MASTER_PLAN journal

**Post-cutover (48h)**

- [ ] Cron backup использует Postgres URL (тот же `/etc/cron.d/booker-backup`, env из скрипта или wrapper)
- [ ] Restore drill на `booker-pg-*.tar.gz` вместе с `.sha256` (quarterly)
- [ ] SQLite файл архивирован, не удалять 30 дней

### Alembic (справка)

Baseline: `apps/api/alembic/versions/*_baseline.py` — все ORM-таблицы из [models.py](../../apps/api/booker_api/models.py).

```bash
docker compose -f infra/docker-compose.yml up -d postgres
export BOOKER_DATABASE_URL=postgresql+psycopg://booker:booker@127.0.0.1:5432/booker
make migrate
cd apps/api && python -m booker_api.seed
make test-api
```

На Postgres API при старте вызывает `alembic upgrade head` ([db.py](../../apps/api/booker_api/db.py)). SQLite (локальные тесты) — `create_all` + `ensure_missing_columns`.

---

## Restore drill — чеклист

| Шаг | Действие | Ожидание |
|-----|----------|----------|
| 1 | Выбрать backup не старше 24h | tar.gz и его `.sha256` скопированы в staging |
| 2 | Выбрать новый restore-каталог | путь ещё не существует; prod-пути не используются |
| 3 | Запустить [restore-drill.sh](../../infra/restore-drill.sh) | exit 0 и строка `restore drill OK` |
| 4 | Проверить отчёт | SHA-256, integrity/FK, schema, Alembic, ключевые таблицы и uploads проверены |
| 5 | Для API smoke указать восстановленную БД | API стартует только на staging; `/health` и ключевые endpoints дают ожидаемый результат |
| 6 | Записать RTO и ограничения | строка в [RESTORE_DRILL_LOG.md](RESTORE_DRILL_LOG.md) |

Целевой RTO пилота: **< 4 ч** (ручной restore на VPS).

```bash
# SQLite pilot: второй аргумент обязан быть новым путём
/opt/booker/infra/restore-drill.sh \
  /var/backups/booker/booker-YYYYMMDDTHHMMSSZ.tar.gz \
  /tmp/booker-restore-drill-YYYYMMDDTHHMMSSZ

# PostgreSQL: создать отдельную пустую staging-БД; скрипт не создаёт и не удаляет БД
createdb --host=RESTORE_HOST --port=5432 --username=RESTORE_USER \
  booker_restore_YYYYMMDD
BOOKER_RESTORE_DATABASE_URL='postgresql://RESTORE_USER@RESTORE_HOST:5432/booker_restore_YYYYMMDD' \
BOOKER_RESTORE_CONFIRM=empty-non-production-database \
/opt/booker/infra/restore-drill.sh \
  /var/backups/booker/booker-pg-YYYYMMDDTHHMMSSZ.tar.gz \
  /tmp/booker-pg-restore-drill-YYYYMMDDTHHMMSSZ
```

PostgreSQL drill намеренно игнорирует `BOOKER_DATABASE_URL`, отказывается работать без отдельного `BOOKER_RESTORE_DATABASE_URL` и точного подтверждения, а также проверяет, что target не содержит пользовательских таблиц. Новый dump восстанавливается через `pg_restore --exit-on-error`. Старый plain-SQL dump запускается через `psql -v ON_ERROR_STOP=1` только с `BOOKER_RESTORE_ALLOW_LEGACY_PLAIN_SQL=trusted-archive` и после запрета database-switch/OS-command конструкций. Если проверка после restore упала, результат — **FAIL**, а частично заполненную staging-БД нужно удалить вручную и создать заново.

PASS фиксируется только при exit code 0 и `restore drill OK`. Отсутствующий/повреждённый payload, несовпавший SHA-256, небезопасный tar member, stale restore-каталог, ошибка integrity/FK, schema/Alembic mismatch, пропавшая ключевая таблица или uploads дают ненулевой exit code. Для старого архива без manifest допустим ограниченный legacy-drill; он не равнозначен v2-проверке, поэтому после восстановления нужно сразу создать новый v2 backup.

Pytest smoke: `apps/api/tests/test_backup_restore.py`.

---

## Не в scope этого плана

- Kubernetes / multi-region
- Live payment rails (U5)
- File upload + AV scan (ClamAV → EXTERNAL_BLOCKED до object storage)

## Статус выполнения (инженерия)

- [x] План и скрипт бэкапа ([backup-booker.sh](../../infra/backup-booker.sh))
- [x] Cron example + install hook в deploy
- [x] Restore drill script + pytest smoke
- [x] Alembic baseline + `make migrate`
- [x] psycopg в зависимостях
- [x] Чеклист аудита хостинга РФ (152-ФЗ)
- [x] Чеклист Postgres cutover + rollback
- [ ] Runtime: cron verify, первый prod backup, restore drill на staging, cutover (см. «Runtime» выше)
