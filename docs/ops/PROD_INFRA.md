# Production data layer — P0

Источник: MASTER_PLAN `p0-prod-infra`. Юридический контекст: [HOSTING_152FZ.md](../legal/HOSTING_152FZ.md).

**Инженерная часть закрыта** (скрипты, Alembic, deploy hook, чеклисты ниже). Остаётся **ops/runtime** — выполнение пунктов в разделе «Runtime (только прод)».

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

---

## Runtime (только прод) — что осталось

Инженерных задач нет. Выполнить на VPS / в облаке РФ:

- [ ] **Cron verify** — после `make deploy`: `cat /etc/cron.d/booker-backup`, дождаться 02:15 MSK или запустить вручную `BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db /opt/booker/infra/backup-booker.sh`
- [ ] **Первый backup + verify** — файл в `/var/backups/booker/booker-*.db.gz`, `gunzip -t`, restore drill на staging (см. ниже)
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

Скрипт: [infra/backup-booker.sh](../../infra/backup-booker.sh) — `sqlite3 .backup` + gzip (SQLite) или `pg_dump` (Postgres), retention 30 дней.

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

```bash
# на VPS, после stop API
export SRC=sqlite:////opt/booker/data/booker.db
export DST=postgresql+psycopg://USER:PASS@HOST:5432/booker

# вариант: pgloader (установить на VPS)
pgloader "${SRC}" "${DST}"

# альтернатива: экспорт через API seed на пустой Postgres + ручной перенос критичных таблиц
# (для пилота с малым объёмом допустим seed + ручной import deals/users)
```

- [ ] Row counts сверены: `users`, `deals`, `events`, `bookings` (±0 или документированный delta)
- [ ] FK / unique constraints без ошибок в логе миграции

**Cutover (окно обслуживания)**

| # | Действие | Команда / проверка |
|---|----------|-------------------|
| C1 | Maintenance page (опционально) | nginx return 503 или статическая заглушка |
| C2 | Stop services | `systemctl stop booker-web booker-api` |
| C3 | Final SQLite backup | `BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db /opt/booker/infra/backup-booker.sh` |
| C4 | Migrate data | pgloader или согласованный скрипт → C5 |
| C5 | Alembic on prod DB | `BOOKER_DATABASE_URL=... alembic upgrade head` (или auto на старте API) |
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
- [ ] Restore drill на `.dump.gz` (quarterly)
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
| 2 | Staging VM или `/opt/booker-restore-test` | изолированный путь, **не prod** |
| 3 | Restore DB | SQLite: [restore-drill.sh](../../infra/restore-drill.sh); Postgres: `gunzip -c booker-pg-*.dump.gz \| pg_restore -d booker_restored` |
| 4 | `BOOKER_DATABASE_URL` → restored | API стартует на staging |
| 5 | `curl /health` + smoke API | 200, ключевые endpoints |
| 6 | Записать RTO, проблемы | строка в журнале MASTER_PLAN |

Целевой RTO пилота: **< 4 ч** (ручной restore на VPS).

```bash
# SQLite pilot
/opt/booker/infra/restore-drill.sh /var/backups/booker/booker-YYYYMMDD.db.gz /tmp/booker-restore-drill
```

Pytest smoke: `apps/api/tests/test_restore_drill.py`.

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
