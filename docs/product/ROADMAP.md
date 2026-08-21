# Дорожная карта

Пилот (код сейчас): identity, каталог+календарь, заявка, Deal Room, hold, оффер с `quote_id`, админ+audit, UI Backstage, Service+залы, буферы слотов, Event Studio, `request.requirement_id` + GET event.requests.

Очередь блупринта v1.0:

| Фаза | Результат |
|------|-----------|
| 0 | Флаги, выжимка блупринта, миграции SQLite — **сделано** |
| 1 | Workspace=Organization, переключение, RBAC owner/admin/manager/viewer — **сделано** |
| P0.3 | `EventTeamRequirement` вместо состава в `notes` — **сделано** |
| 2 | Taxonomy, Service, объект/зал — **сделано** |
| 3 | Resource + буферы слотов — **сделано** (поля на AvailabilitySlot, overlap с буфером) |
| 4 | Event Studio мультисостав — **сделано** (qty, PUT requirements, страница события) |
| 5 | Deal на позицию, Event Control Room — **сделано** (request.requirement_id, GET event.requests, заявка из каталога в роль) |
| 6–8 | Документы, коммерция, рост — **не в этом деплое** (нет 3D, Turbo, Protect, живого эквайринга) |

Фаза 3 буферы: на существующем AvailabilitySlot (artist|hall), без новой таблицы Resource.

Следующие: фазы 6–8 (документы, коммерция, рост). Не в пилоте: 3D, Turbo, Protect, живой эквайринг.

Отложено: 3D, Turbo, AI в спорах, Protect, эквайринг до юриста, смена SQLite→Postgres в этом спринте.
