# Аналитика пилота

События продукта пишутся в `audit_logs` через `audit()` на сервере. Журнал append-only; удаление запрещено.

## Воронка сделки

| action | Когда | entity_type |
|--------|-------|-------------|
| `requirement.created` | Позиция добавлена в состав события | `requirement` |
| `request.created` | Заявка отправлена исполнителю/площадке | `request` |
| `offer.created` | Первый оффер по заявке | `offer` |
| `offer.version` | Новая версия оффера (цена с сервера) | `offer` |
| `offer.ack` | Сторона подтвердила оффер | `offer` |
| `hold.created` | Дата удержана | `booking` |
| `hold.expired` | Удержание истекло (фон) | `booking` |
| `contract.created` | Договор сгенерирован | `contract` |
| `contract.signed` | Договор подписан OTP | `contract` |
| `payment.created` | Платёж инициирован | `payment` |
| `payment.webhook` | Webhook провайдера | `payment` |
| `payment.refunded` | Возврат (админ) | `payment` |

## Supply и каталог

| action | Когда | entity_type |
|--------|-------|-------------|
| `service.created` | POST `/services` | `service` |
| `hall.created` | POST `/venues/{id}/halls` | `hall` |
| `slot.created` | Слот календаря открыт | `slot` |

## Identity и workspace

| action | Когда | entity_type |
|--------|-------|-------------|
| `user.registered` | Регистрация | `user` |
| `org.created` | Создание организации | `organization` |
| `workspace.switched` | Смена активного workspace | `user` |

## Операции и модерация

| action | Когда | entity_type |
|--------|-------|-------------|
| `verification.decided` | Решение по верификации | `artist` / `venue` |
| `dispute.opened` | Открыт спор | `booking` |
| `client.event` | Клиентское событие UI (allowlist) | `client_event` |

### Клиентские события (allowlist)

| name | Когда | Группа |
|------|-------|--------|
| `page.view` | Переход по страницам | discovery |
| `search.performed` | Поиск в каталоге | discovery |
| `deal.room.opened` | Открыт Deal Room | discovery |
| `event.studio.started` | Вход в Event Studio | studio |
| `event.studio.completed` | Отправка заявки из Studio | studio |
| `cabinet.viewed` | Загрузка кабинета | cabinet |
| `cabinet.offer_sent` | Supply отправил оффер | cabinet |
| `cabinet.service_created` | Создана услуга | cabinet |
| `cabinet.ical_imported` | Импорт iCal | cabinet |
| `cabinet.vacation_set` | Включён отпуск | cabinet |

Клиент: `POST /analytics/events` (auth). Web: `trackClientEvent()` в `apps/web/lib/api.ts`.

Просмотр: `GET /admin/audit` (platform admin). Агрегаты воронки: `GET /admin/metrics` — counts и unique_entities по action за 7/30 дней; блок `dashboards` — воронка (конверсия по шагам), ликвидность (поиск→сделка, заявка→оффер), утечки (брошенный Studio, заявки без оффера, истёкшие hold).
