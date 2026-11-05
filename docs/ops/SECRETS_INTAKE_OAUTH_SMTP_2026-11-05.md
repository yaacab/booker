# Secrets intake — OAuth + SMTP (2026-11-05)

Owner GO на предоставление секретов получен. Значения **не** класть в Git / чат-лог без необходимости. Предпочтительно: GitHub Actions secrets + файл на staging host `0600`.

## OWN-OAUTH-YANDEX-VK

| Ключ | Назначение | Redirect (staging) |
|---|---|---|
| `YANDEX_OAUTH_CLIENT_ID` | Yandex ID | `https://staging.bukergo.ru/api/auth/yandex/callback` (уточнить по коду) |
| `YANDEX_OAUTH_CLIENT_SECRET` | Yandex secret | — |
| `VK_OAUTH_CLIENT_ID` | VK ID | `https://staging.bukergo.ru/api/auth/vk/callback` |
| `VK_OAUTH_CLIENT_SECRET` | VK secret | — |

После значений: обновить fail-closed stubs → live adapters только на staging; AUTH-04 остаётся blocked на `REL-STAGING` до apply миграций.

## OWN-SMTP

| Ключ | Пример |
|---|---|
| `SMTP_HOST` | `smtp.yandex.ru` / provider |
| `SMTP_PORT` | `465` или `587` |
| `SMTP_USER` | mailbox |
| `SMTP_PASSWORD` | app-password |
| `SMTP_FROM` | `noreply@bukergo.ru` |
| `SMTP_TLS` | true |

Проверка: одно security/recovery письмо на staging → evidence в `docs/ops/`. Без этого `REL-SMTP` / S06 не DONE.

## Как передать агенту

1. GitHub → Settings → Secrets (repo) **или**
2. Файл на staging: `/etc/booker-staging/secrets.env` mode `0600` **или**
3. В чате одноразово (потом rotate)

Пока пусто — задачи `OWN-OAUTH-YANDEX-VK` и `OWN-SMTP` = TODO.
