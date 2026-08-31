# Дорожная карта

Пилот (код сейчас): identity, каталог+календарь, заявка, Deal Room, hold, оффер с `quote_id`, админ+audit, UI Backstage, Service+залы, буферы слотов, Event Studio, `request.requirement_id` + GET event.requests, связь Deal Room ↔ событие, факты профиля (сделки).

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
| 6–8 | Документы, коммерция, рост — **отложено** (CONTRACT: нет 3D, Turbo, Protect, живого эквайринга; stub-платежи и договор OTP уже есть) |

Фаза 3 буферы: на существующем AvailabilitySlot (artist|hall), без новой таблицы Resource.

Пилот закрыт по фазам 0–5. Следующий спринт: фазы 6–8 после юриста и платёжного партнёра.

## P1 supply console (план v2.0)

| ID | Задача | Статус |
|----|--------|--------|
| C1 | Редактор состава `/events/[id]` | **сделано** |
| C2 | UI управления Service | **сделано** |
| C3 | Создание залов площадки | **сделано** |
| C4 | Верификация venues в админке | **сделано** |
| C5 | `confirm_another_workspace` в UI | **сделано** |
| C6 | Analytics taxonomy + Control Room polish + e2e flow | **сделано** |

Деплой P1 supply console: **сделано** (af2bf06 — C1–C5; d1bdbe3 — C6).

Отложено: 3D, Turbo, AI в спорах, Protect, эквайринг до юриста, смена SQLite→Postgres в этом спринте.
