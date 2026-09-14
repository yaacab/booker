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

## Commercial v3, первый инкремент (2026-09-12)

- `pricing.viewed` — client.event allowlist; просмотр страницы тарифов.
- `subscription.checkout_started` — сервер создал BillingOrder, включая disabled
  checkout. Не означает оплату или активацию.
- `subscription.activated` — только после проверенного paid notification.
- `subscription.cancelled` — отмена автопродления/изменение на конец периода;
  effective_at в payload, текущий доступ сохраняется до этой даты.
- `subscription.expired` — срок истёк; идемпотентный переход.
- `subscription.admin_grant` — ручной support grant/revoke с причиной, не revenue.
- `commercial.plan_changed` — старая и новая ревизии catalog с причиной.
- `billing.paid`, `billing.failed`, `billing.refunded`, `billing.cancelled` —
  подтверждённые переходы заказа. Provider=stub исключается из денежных поступлений.

Оставшаяся taxonomy/атрибуция и dashboards принимаются в prelaunch отдельно.

### Paid promotion (commercial v3)

Серверные события: `promotion.created`, `promotion.started`, `promotion.expired`,
`promotion.impression`, `promotion.click`, `promotion.request`, `promotion.booking`.
Дополнительно: `promotion.cancelled`, `promotion.rejected`,
`commercial.promotion_price_changed`. Token выдачи связан с кампанией, затем с
реальной заявкой и Confirmed booking. CTR = clicks/impressions, null при отсутствии
показов; повторные сигналы одного token дедуплицируются. Это атрибуция по переходу
в пределах 7 дней, не доказательство причинного эффекта рекламы.

### Growth Center

`DiscoverySignal` хранит наблюдения `impression`, `profile_view`, `favorite`.
Показы дедуплицируются по профилю, случайному ключу сессии и дню UTC; уникальные
просмотры — по ключу сессии за период. В базе только SHA-256 случайного UUID,
без IP/контактов; browser Do Not Track отключает клиентские наблюдения.
Просмотры своей команды исключены. Favorite записывает сервер после фактического
добавления, клиент не может отправить этот вид сигнала напрямую. Наблюдения
не дают права менять verified, цены, деньги или состояние сделки.

Заявки образуют когорту по `Request.created_at`; предложение, hold, Confirmed,
Completed считаются по связанным данным этой когорты. Отношения объёмов
impression/profile/request не заявляются пользовательской когортной конверсией.
Медиана ответа — время до первого Offer; отсутствие ответа даёт null, а не
обещание скорости. Confirmed honorarium — сумма активных immutable OfferVersion
у Confirmed/InProgress/Completed, отдельно от фактических выплат.

`request.loss_reason` — явная отметка стороны уже закрытой заявки. `price` может
указать только customer writer. Пока отметки нет, причина unknown. Чужая сторона
не может перезаписать уже зафиксированную причину. Истечение request/offer не
выводится из молчания; без соответствующего факта остаётся unknown.

7/30 дней доступны Free; 90 — Pro; 365 и export — Premium. Resolver проверяет
актуальный срок подписки на каждый API вызов. Benchmark доступен Premium только
для одного своего профиля; минимум 10 похожих профилей из 10 других организаций.
Возвращаются только агрегат и описание группы, без ID/имён/отдельных показателей.
Открытые даты рассчитываются по московскому календарю с busy overlays каждого
ресурса отдельно. `ARTIST_GROWTH=false` отключает API и сбор новых наблюдений.

### Opportunities

`brief.published` фиксирует явную публикацию публичного снимка;
`brief.response_created` — ручной отклик организации с выбранным профилем,
без создания оффера/брони. `opportunity.filter_saved` и
`opportunity.filter_removed` фиксируют личные фильтры и отзыв уведомлений.
`opportunity.alerted` — однократная in-app доставка подходящего брифа пользователю
с действующим entitlement и явным согласием. Дедупликация — brief/user.
Просмотр ленты сам по себе не является откликом или лидом; приватные бюджеты
событий не входят в публичную выдачу/уведомления. Все уровни подписки используют
одинаковые правила соответствия; платежи не влияют на score.

### Витрина

`artist.presentation_updated` — сохранение новой версии собственным writer;
содержит номер версии и факт подтверждения прав на материалы. Повтор идентичного
PUT не создаёт второй audit. Витрина использует прежние discovery profile-view и
favorite сигналы; изменение оформления не меняет trust metrics. Media views
внешнего видеосервиса не выдаются за измеренные просмотры на Букере.

### Совместимость

`compatibility.viewed` — выполненная серверная проверка пары artist/venue/hall;
содержит статус и optional event_id только во внутреннем audit. Приватный event
доступен только его организации. Публичный результат не содержит контактов,
платежей или чужих событий. `hall.technical_updated` хранит версию и имена
изменённых полей, без копии произвольного текста ограничений. Идентичный PUT
не создаёт повторное изменение. Просмотр совместимости не равен заявке/сделке.

### Ориентир Event Studio

`event.estimate_viewed` содержит только число выбранных/имеющих публичный тариф
участников и полноту расчёта. Это не quote, revenue, request или подтверждение
доступности. Публичный endpoint не раскрывает тарифы скрытых площадок.

### Создание события

`event.created` фиксирует один committed Event: организация, число позиций,
наличие окончания. Текст заметок, ключ отправки и контакты в payload не входят.
Повторы через EventCommandReceipt не создают вторую запись event.created или
request.created. Browser event.studio.completed остаётся UI-сигналом и не
заменяет число сохранённых сервером событий.


### Подбор и предварительный состав

`event.matching_viewed` — авторизованный серверный расчёт, включая ручную
перепроверку; payload содержит состояние окна/ролей и число обязательных позиций.
Это не уникальные просмотры, заявка, бронь или EventReadiness.
`event.plan_updated` — сохранённая новая revision, число выбранных позиций;
одинаковый повтор не создаёт повторный audit. `event.planning_updated` — имена
изменённых полей окончания/бюджета без свободного текста. Все три события остаются
во внутреннем audit организации, не публикуются как discovery-метрики.


### Бюджет события

`event.budget_viewed` — авторизованное чтение расчёта бюджета; payload содержит
только state (no_budget/partial/within_budget/over_budget), без суммы, контактов,
заметок и состава. Это не платёж, выручка или принятие оффера. Повторное чтение
может создавать новый view; счётчик не следует трактовать как уникальных клиентов.


### Готовность события

`event.readiness_viewed` содержит только state авторизованной сводки события.
`event.readiness_list_viewed` содержит число событий в сводке организации
(до 12); не копирует участников, платежи, документы, технические тексты или
контакты. Повторное чтение — новый просмотр, не уникальная конверсия. Readiness
не подтверждает выручку/оплату/доступность отдельным audit-событием: источники
таких фактов остаются доменными событиями сделки и платежа.


### Compare V2 и факты площадки

`compare.opened` — успешное серверное чтение сравнения 2–4 публичных профилей.
Payload: `target_type`, `count`, `with_event`; без списка участников, дат, гостей,
тарифов, отзывов, контактов или свободного текста. Изменение параметров/повтор
чтения может создать новое событие; это не уникальный пользователь и не заявка.
Просмотр с событием требует членства в его организации. Сохранение участника
через Compare использует существующий `event.plan_updated` и его revision/RBAC.

Количество завершённых сделок и измеренное время первого предложения площадки
учитывают как прямые заявки на площадку, так и заявки на её конкретные залы.
Профили одного владельца не делят эти показатели. Деньги за подписку или
продвижение не влияют на выборку, оценки отзывов или Verified.

### Совместные подборки

- `shortlist.created`: тип кандидатов, число, признак совместного режима и привязки
  к событию. Идемпотентное повторение создания не даёт второй записи.
- `shortlist.viewed`: успешное гостевое чтение одной действующей ссылки;
  повтор/обновление — новый просмотр, не уникальный участник.
- `shortlist.guest_joined`: создан гостевой участник одной подборки; повтор с тем
  же ключом не создаёт второго участника.
- `shortlist.feedback_updated`: реакция, наличие комментария и revision;
  одинаковое повторение не дублирует событие или голос.
- `shortlist.results_viewed`: число подборок в авторизованном чтении организации.
- `shortlist.revoked`: однократный отзыв ссылки.

В payload нет гостевых имён, текстов, токенов приглашения, ключей устройства,
контактов, бюджета, документов или приватного названия события. Эти события не
являются отзывами, оценкой исполнителя, конверсией в сделку или изменением состава.
Счётчики реакций отражают гостевые устройства; уникальность людей не подтверждена.

### Повтор события

`repeat_event.viewed` — авторизованное чтение preview Completed.
`repeat_event.created` — один новый Draft, payload содержит число ролей и
предпочитаемых участников. Идемпотентный повтор не создаёт второго события/audit.
`repeat_event.preferences_viewed` — повторная проверка предпочтений на новом
событии, payload содержит только их число. Участники, даты, тексты, стоимость,
документы и подписи в audit payload не копируются. Добавление предпочтения в
предварительный состав использует `event.plan_updated`; это ещё не новая заявка.

### Replacement UX

- `replacement.viewed`: authorized organization member opened replacement for a role; open slot and cancellation counts only.
- `replacement.requested`: writer explicitly requested a currently eligible replacement; requirement and resource identifiers. In the same transaction as `request.created` and the durable command receipt. Retries do not emit a second event.
- Candidate ordering is alphabetical, without paid or opaque preference. Availability is a current calendar check, not a reservation or replacement guarantee.
