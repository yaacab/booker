# Source of truth — published live (2026-10-31)

**Готовность (реестр без пересчёта):** FULL 59,00% / MVP 56,00% / Design 15,00%.

## Что реально работает на сервере

| Часть | Release id | Локальный эталон | Файлов |
|---|---|---|---:|
| Frontend | `20261023-prod-fixes-w6b` | `outputs/prod-fixes-20261020/live-base` @ `28325b3` | 289 / 289 |
| Backend | `20261023-qa-wave2` | `outputs/api-catalog-b-20261020/base` @ `ba7ce54` | 139 / 139 |

- Публичный домен: `https://bukergo.ru`
- Next build id: `abgfnwzG7icOocGxuLQGV`
- Платежи: отключены (пилот)
- Legal draft: `2026-08-18-draft`

Проверка 31.10.2026: SHA-256 всех отслеживаемых файлов эталонов совпали с сервером. «Грязное» дерево в эталонах до pin-коммитов **уже было на production** — незакоммиченный статус не означал неопубликованность.

## Ветка канона в основном репозитории

- Branch: `sync/live-canonical-20261031`
- Base: `codex/scene01-live-home-20261015` (`a359bc8`)
- Import: полный `apps/web` из live-base + полный набор файлов api-catalog в `apps/api`
- Verification: 289/289 web и 139/139 api байт-в-байт с эталонами

## Что отстаёт / не канон

| Путь | Статус |
|---|---|
| `/home/art67/booker` @ `0771cd7` (delivery) | **отстаёт** от live; не использовать как prod checkout |
| `origin/master` @ `ca20ac2` | старый; не равен live |
| Старые worktree / прототипы / overlays | вне этого среза; не деплоить вместо канона |

## Правила

1. **Не деплоить** с delivery/master/произвольного worktree без сверки с этим документом.
2. Правки к live начинать от `sync/live-canonical-20261031` (или обновлённого наследника).
3. Production не трогать без отдельного GO владельца.
4. Каталог «0 артистов» на проде — данные/publication gate, не рассинхрон фронта с бэком в этих 289+139 файлах.

## Следующий контролируемый шаг (не выполнен здесь)

- PR канона → согласованная base; merge только по GO
- Отдельное расследование пустого каталога (seed / `publication_enabled` / moderation)
- Staging VPS и пересчёт критериев — по-прежнему внешние gates
