# Метаданные сеанса (UA / IP / last_seen) — локально

**Дата:** 2026-11-03  
**Уровень:** локально (не staging / не production)  
**Срез AUTH-04:** поля на `session_tokens` для списка в профиле

## Схема

Alembic `c13a45b67c89` после `b12f34e56a78`:

- `user_agent` VARCHAR(512) NULL
- `client_ip` VARCHAR(64) NULL  
- `last_seen_at` timestamptz NULL

SQLite `ensure_missing_columns` дублирует колонки для `create_all` тестов.

## Поведение

- `issue_token(..., request=)` пишет UA/IP/`last_seen_at` при login/register/Telegram complete.
- `auth_context` обновляет `last_seen_at` (и UA/IP) не чаще раза в 60 с отдельным commit.
- `GET /me/sessions` отдаёт поля; web `ActiveSessions` показывает грубый ярлык клиента и IP.

IP через тот же trusted-proxy разбор, что rate limit (`X-Real-IP` только от доверенного peer).

## Проверка

```bash
cd apps/api && uv run --extra dev pytest tests/test_sessions_self_service.py tests/test_identity.py -q
```

17 PASS в этом наборе.

## Не закрывает

- Применение миграции к фактической/staging БД без sealed backup + restore.
- Геолокацию, fingerprint, Yandex/VK OAuth.
