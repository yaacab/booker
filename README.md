# Букер (`booker`)

Платформа бронирования артистов и площадок. Публичное имя — **Букер**. Не часть THE AIV.

Публичные домены (Reg.ru, до 18.08.2027): канон [bukergo.ru](https://bukergo.ru), дубли `bookergo.ru` и `bukergo.online` редиректят. Как прописать DNS: [`docs/ops/DOMAINS.md`](docs/ops/DOMAINS.md).

## Стек

- `apps/web` — Next.js App Router
- `apps/api` — FastAPI
- `infra/docker-compose.yml` — Postgres 16 + Redis
- `packages/shared-types` — статусы и токены бренда

## Команды

```bash
# API
cd apps/api && pip install -e ".[dev]" && pytest -q
uvicorn booker_api.main:app --reload --app-dir apps/api

# Web
cd apps/web && npm install && npm run dev
```

Локальная БД для разработки: SQLite по умолчанию. Postgres:

```bash
docker compose -f infra/docker-compose.yml up -d
export BOOKER_DATABASE_URL=postgresql+psycopg://booker:booker@127.0.0.1:5432/booker
```

Локальный контур:

```bash
make seed
cd apps/api && ../../.venv/bin/uvicorn booker_api.main:app --reload
cd apps/web && npm run dev
```

Повторный выкат на VPS: `make deploy` (ключ `~/.ssh/booker_deploy_key`, хост `5.45.112.180:2222`). HTTPS: на сервере `bash /opt/booker/infra/issue-cert.sh`, когда `dig bukergo.ru` покажет этот IP.

Путь: каталог → профиль DJ Nova → заявка → кабинет артиста → оффер → Deal Room → ack → hold → договор OTP `123456` → stub-оплата.

- Цена только с сервера (`quote_id`).
- Нет выдачи без календаря.
- AI не решает споры.
- Не обещать страхование.
