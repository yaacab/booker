# Сессии профиля — self-service (локально)

**Дата:** 2026-11-03  
**Уровень:** локально  
**Срез AUTH-04:** список сеансов, отзыв чужих, флаги configured у провайдеров

## API

| Метод | Путь | Поведение |
|---|---|---|
| GET | `/me/sessions` | Список сеансов; `current` по текущему bearer |
| POST | `/me/sessions/revoke-others` | Удаляет все кроме текущей; audit + security notice |
| DELETE | `/me/sessions/{id}` | Удаляет чужой сеанс; текущий → 409 (нужен logout) |
| GET | `/me/identities` | + `providers.{telegram,yandex,vk}.configured` |

`id` сеанса — хеш токена (не сырой bearer).

## Web

Профиль: `ActiveSessions` рядом с `LinkedIdentities`.

## Проверка

```bash
cd apps/api && uv run --extra dev pytest tests/test_sessions_self_service.py -q
```

5 PASS. Yandex/VK OAuth и nullable credentials по-прежнему открыты.
