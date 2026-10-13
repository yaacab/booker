# Production data layer — P0

Источник: MASTER_PLAN `p0-prod-infra`. Юридический контекст: [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md).

**Инженерная часть подготовлена локально**, но production readiness требует runtime-проверок и согласованного snapshot DB+uploads. Оставшиеся пункты перечислены в разделе «Runtime (только прод)».

## Текущее состояние (пилот 2026-09)

| Компонент | Сейчас | Целевое P0 |
|-----------|--------|------------|
| API | VPS `5.45.112.180`, systemd `booker-api` | то же |
| Web | nginx + `booker-web` (Next.js) | то же |
| БД | SQLite `/opt/booker/data/booker.db` | Managed Postgres 16 в РФ |
| Redis | нет | Managed Redis (сессии/rate limit при горизонтальном API) |
| Object storage | нет (файлы не принимаем) | Yandex Object Storage при появлении upload |
| Backups | скрипт + cron в deploy | daily + retention 30d, **verify на проде** |
| Restore drill | скрипт + pytest smoke | quarterly на staging, документировать RTO |
| Alembic | baseline `a44d171` | `alembic upgrade head` на Postgres |

`BOOKER_DATABASE_URL` в [config.py](../../apps/api/booker_api/config.py); локальный Postgres: `infra/docker-compose.yml`.

Перед следующим применением `infra/systemd/booker-api.service` обязателен [production configuration gate](PRODUCTION_CONFIG_GATE.md): новый шаблон задаёт `BOOKER_RUNTIME_ENV=production` и не стартует с default/отсутствующим webhook secret, `stub`, выключенной admin 2FA, dev transport или localhost CORS. Текущий установленный unit и защищённый env-файл не проверены; изменение шаблона само по себе не означает готовности к deploy.

---

## Runtime (только прод) — что осталось

Локальный backup/restore путь проверен на синтетической SQLite, но инженерные и runtime-гейты ниже остаются. Выполнить на VPS / в облаке РФ:

- [ ] **Cron verify** — после `make deploy`: `cat /etc/cron.d/booker-backup`, дождаться 02:15 MSK или запустить вручную `/opt/booker/infra/run-booker-backup.sh`; wrapper читает `/etc/booker/booker-api.env`
- [ ] **Первый backup + verify** — архив в `/var/backups/booker/booker-*.tar.gz`, `tar -tzf`, restore drill на staging (см. ниже)
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

Wrapper: [infra/run-booker-backup.sh](../../infra/run-booker-backup.sh) читает защищённый runtime env API. Он **не останавливает API по умолчанию**: SQLite online backup и `pg_dump` выполняются при работающем сервисе; изменившиеся во время копирования uploads отклоняют backup. `BOOKER_BACKUP_QUIESCE_SERVICE` включает явную остановку указанного сервиса, если это требуется для согласованного snapshot; этот режим требует отдельной операционной проверки. Скрипт [infra/backup-booker.sh](../../infra/backup-booker.sh) делает SQLite online backup через Python, `pg_dump --format=custom` для Postgres, добавляет проверенную копию uploads и manifest в legacy `tar.gz` по умолчанию. Опциональный authenticated/encrypted `.bke` и требуемый внешний Python с `cryptography` описаны в [BACKUP_SEALED.md](BACKUP_SEALED.md); это **локально испытанный формат, не включённый production gate**. Перед публикацией архив проверяется; повтор в ту же секунду получает уникальное имя, при сбое `.partial` удаляется. Retention: `find -mtime +N` по mtime в backup-каталоге после успешного backup для обоих форматов; `BOOKER_BACKUP_RETENTION_DAYS` принимает 1–3650, `BOOKER_BACKUP_RETENTION_DRY_RUN=1` показывает кандидатов без удаления. **Полного dry-run без создания архива пока нет.**

Архив `tar.gz` **не зашифрован**, а SHA-256 manifest хранится внутри него и обнаруживает случайную порчу, но не подмену архива с пересчитанным manifest. Локальные права `0700/0600` не защищают скопированный архив. Off-site передача и хранение ПДн требуют отдельного защищённого канала, шифрования с управлением ключами и проверки восстановления; пример `rsync` ниже не является готовым безопасным регламентом.

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
- [ ] Секрет `BOOKER_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/booker?sslmode=require` — в `/etc/booker/booker-api.env` с `root:root 0600`, не в git; его читают API и backup wrapper
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

- [ ] Row counts сверены: `users`, `deals`, `events`, `bookings` (±0 или документированный delta)
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

- [ ] Cron backup использует Postgres URL из `/etc/booker/booker-api.env`; проверить до открытия трафика
- [ ] Restore drill на `booker-pg-*.tar.gz` (quarterly)
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
| 1 | Выбрать backup не старше 24h | файл `.gz` в `/var/backups/booker/` |
| 2 | Staging VM или новый каталог под `/tmp/booker-restore-*` | изолированный путь, **не prod** |
| 3 | Restore DB | SQLite: [restore-drill.sh](../../infra/restore-drill.sh); Postgres: создать отдельную пустую staging-БД `booker_restored`, проверить host/name, распаковать `booker.dump`, затем `pg_restore --exit-on-error --no-owner --dbname=booker_restored booker.dump` |
| 4 | `BOOKER_DATABASE_URL` → restored | API стартует на staging |
| 5 | `curl /health` + smoke API | 200, ключевые endpoints |
| 6 | Записать RTO, проблемы | строка в журнале MASTER_PLAN |

Целевой RTO пилота: **< 4 ч** (ручной restore на VPS).

```bash
# SQLite pilot
/opt/booker/infra/restore-drill.sh /var/backups/booker/booker-YYYYMMDDTHHMMSSZ.tar.gz /tmp/booker-restore-drill
```

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
