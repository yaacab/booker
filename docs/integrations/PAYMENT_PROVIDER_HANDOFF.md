# Подключение платёжного провайдера

Статус: инженерная подготовка продолжается. Этот документ описывает текущую
границу интеграции; он не подтверждает готовность production и не выбирает партнёра.

## Где подключать

- Commerce: `apps/api/booker_api/commerce/provider.py`, протокол `CommerceProvider`,
  фабрика `get_provider()`. Реализовать выбранный adapter отдельным классом.
- Бронирования: `apps/api/booker_api/payments/adapter.py`, `PaymentAdapter`,
  фабрика `get_payment_adapter()`. Существующий `live.py` fail-closed.
- Заказы/активация: `commerce/orders.py`. Не активировать подписку внутри frontend
  или provider.create_checkout; активация происходит после проверенного события.
- Booking status machine и quote_id: `routers/deals.py`, `routers/payments.py`.

Нельзя объединять billing subscription и Booking в одну state machine.
Адаптеры могут использовать один SDK партнёра и одну реализацию signature verification,
но бизнес-переходы сохраняются в своих доменах.

## Переменные

Реальные значения только в secret store / systemd env, никогда в git.

- `BOOKER_ENVIRONMENT`: production по умолчанию; dev/test для локального стенда.
- `BOOKER_COMMERCE_PROVIDER`: disabled по умолчанию; имя выбранного live adapter
  после реализации. Неизвестное имя сейчас приводит к disabled.
- `BOOKER_COMMERCE_ALLOW_STUB`: false по умолчанию. Работает только dev/test.
- `BOOKER_COMMERCE_WEBHOOK_SECRET`: отдельный ключ подписи commerce notifications.
  Для stub необходима длина не менее 32 символов; тестовый пример из CI не секрет.
- Booking: `BOOKER_PAYMENT_PROVIDER`, `BOOKER_PAYMENT_MERCHANT_ID`,
  `BOOKER_PAYMENT_PUBLIC_KEY`, `BOOKER_PAYMENT_SECRET_KEY`, `BOOKER_WEBHOOK_SECRET`.
- Юридические gates: `BOOKER_LAWYER_APPROVAL_DATE`, `BOOKER_PAYMENT_FLOW_APPROVAL`
  и реестр [OWNER_INPUTS](../OWNER_INPUTS.md).
- Feature switches: `BOOKER_COMMERCIAL_PLANS`, `BOOKER_PAID_PROMOTION`,
  `BOOKER_ARTIST_GROWTH`, `BOOKER_OPPORTUNITIES`, `BOOKER_SMART_MATCHING`,
  `BOOKER_COMPATIBILITY`, `BOOKER_CUSTOMER_BUSINESS`.

## Методы commerce adapter

- `create_checkout(order_id, amount_rub, currency, idempotency_key)` → Checkout:
  provider reference, pending status, checkout URL.
- `get_payment_status(reference)` → подтверждённое состояние для сверки.
- `verify_webhook(raw_payload, signature)` → ProviderEvent с event_id/order_id/
  reference/status/amount_rub/currency. Проверять подпись исходных байтов,
  merchant/account и все поля партнёра; не доверять frontend redirect.
- `refund(reference, amount_rub, idempotency_key)` → pending до подтверждения.
- `create_subscription(order_id, amount_rub, currency, billing_period,
  idempotency_key)` → Checkout + subscription_reference.
- `cancel_subscription(reference)` → прекращение будущих списаний у партнёра.

SDK партнёра конвертирует integer RUB в свои minor units только на внешней границе.
Проверить округление, валюту и точное соответствие суммы до settlement.

## Потоки

Booking: OfferVersion → взаимный ack → hold → подписи договора →
серверный Payment → checkout → проверенный webhook → подтверждённая Booking.
Неуспешная оплата не подтверждает бронь. Истечение hold и двойное бронирование
обрабатываются существующим доменом; provider не должен обходить эти проверки.

Subscription: выбор тарифа → BillingOrder с неизменным plan/price snapshot →
checkout → signed paid → active Subscription. Повышение открывает новый полный
период; понижение/отмена сохраняются до конца текущего. Месяц считается календарно.
Следующий платный период требует нового оплаченного BillingOrder; recurring
adapter должен выдавать стабильный ID периода, idempotency key и подписанный
результат, а не продлевать доступ на основе browser callback.

Promotion: отдельный one-time BillingOrder; запуск campaign после paid.
Длительность/цена берутся из server catalog, paid не отменяет eligibility/availability.
Campaign lifecycle и включённые месячные credits принимаются в рамках prelaunch.

## Webhook и возврат

Commerce endpoint: `POST /commerce/webhook`, `X-Commerce-Signature`.
Нормализованные статусы сейчас: paid / failed / refunded.
Точное соответствие provider, reference, amount и currency обязательно.
Дубликат event_id с тем же payload возвращает сохранённый результат;
тот же event_id с другим payload — конфликт. Late failed после paid запрещён.
Полный refund последнего subscription order отзывает его доступ. Частичные
refunds/пропорциональные компенсации нельзя выдавать за выполненные этим потоком.
Их отдельная модель требуется при выборе партнёра/утверждённых правил возврата.
Booking refunds имеют audit и проверку второго admin ID; ограничения этого
механизма описаны ниже, полноценное второе подтверждение ещё требуется.

Верифицированный capture, manual grant, stub payment и начисленная fee —
разные факты. Реальный GMV/revenue не включает тестовые заказы и manual grants.

## Sandbox acceptance перед live switch

Проверить create + retry, duplicate/out-of-order webhooks, неверную подпись,
merchant mismatch, неверную сумму/валюту, capture failure, timeout + reconciliation,
полный/частичный возврат по согласованному контракту, renewal success/failure,
отмену автопродления, истечение доступа, cross-org authorization.
Запустить booking regression, commerce API tests и все commercial E2E на sandbox.
Сохранить фактические результаты; stub E2E не доказывает работу live provider.

## Включение production

Только после внешних gates: юрист, оператор/реквизиты, партнёр и merchant secrets,
РКН/152-ФЗ, инфраструктура и storage, sandbox acceptance. Включить выбранный
adapter именем провайдера и явным live gate, отключить все test paths и default
webhook secret. Выполнить release/сверку по отдельному разрешению владельца.
В текущей задаче live switch, production deploy, DNS и merge запрещены.

## Защита старого booking checkout (prelaunch)

`BOOKER_PAYMENT_PROVIDER=disabled` и `BOOKER_PAYMENT_ALLOW_STUB=false` — defaults.
Stub требует одновременно `BOOKER_ENVIRONMENT=dev|development|test`, явного
`BOOKER_PAYMENT_PROVIDER=stub` и opt-in. Даже подписанный stub webhook в production
отклоняется. `payment_live_enabled()` остаётся false до регистрации реального
adapter; наличие merchant ID само по себе не означает работоспособность платежей.
External режим сохранён: перевод подтверждает platform admin с 2FA и audit.

Checkout проверяет customer organization/writer до обработки повторов. Ключ
идемпотентности хешируется со scope booking; повторный checkout другой кнопкой
возвращает существующий платёж этой брони. Payment и booking блокируются перед
соответствующими переходами. После удержания даты условия оффера заморожены.
Подтверждённая оплата потребляет hold; поздний failed не отменяет succeeded.

Capture после истечения резерва учитывается как платёжный факт, но не подтверждает
дату. Создаётся `payment.reservation_conflict`; Deal Room сообщает необходимость
оператора/согласования/возврата. Интеграция обязана доставлять этот случай в сверку.
Оператор не должен повторно подтверждать уже занятый слот. Нельзя интерпретировать
HTTP 200 webhook как обещание Confirmed: проверяется возвращённый booking_status.

## Проверенная граница интеграции на 15 сентября 2026

Следующие ограничения установлены чтением текущих реализаций, а не проверкой
реального PSP. Они входят в незавершённую инженерную работу перед live и не
снимаются заполнением переменных окружения.

### Booking adapter и входящее событие

`PaymentAdapter` сейчас имеет методы:

- `create_session(payment_id, amount_rub, idempotency_key, booking_id)` возвращает
  `PaymentSession(provider, payment_id, status, checkout_url, provider_reference)`.
- `verify_webhook(event_id, payment_id, status, signature)` возвращает
  `WebhookEvent(event_id, payment_id, status)`.
- `normalize_idempotency_key(key)` нормализует ключ до booking scope.
- `refund(payment_id, amount_rub, total_rub, idempotency_key)` возвращает
  `RefundOutcome(refund_id, amount_rub, kind, status)`.
- `LedgerHooks.on_session_created/on_capture/on_refund` — интерфейс событий;
  `NoOpLedgerHooks` не является бухгалтерским регистром или банковской сверкой.

Booking endpoint — `POST /payments/webhook`; текущий `WebhookIn` передаёт
signature в JSON. Этот формат используется stub и **не является** готовым
контрактом webhook выбранного PSP. В нём нет суммы, валюты, merchant ID и исходного
payload. Для реального адаптера нужен проверяемый вход исходных байтов и headers
партнёра с проверкой merchant/reference/amount/currency до доменного перехода.
Нельзя просто подставить реальную подпись в существующий stub JSON.

`POST /bookings/{booking_id}/payments` сейчас возвращает id/status/amount/provider.
Хотя `PaymentSession` допускает checkout_url и provider_reference, маршрут пока
не сохраняет и не возвращает эти поля. Нужны их устойчивое хранение, одинаковый
результат retry и checkout UI; существующий ответ не доказывает готовность redirect.

Порядок блокировок capture пока отличается от Event → resource → slot,
применяемого hold/cancel/contracts. До live требуется проверить и согласовать
capture/cancel/expiry на PostgreSQL, сохраняя платёжный факт при конфликте даты.
Это отдельный пробел; тесты конкурентных hold не доказывают безопасность capture.

### Возвраты и подтверждения операторов

Commerce нормализует **полный** возврат в `ProviderEvent.status=refunded` с суммой
исходного заказа. Это не поддержка произвольного partial refund. Наличие метода
`CommerceProvider.refund` само по себе не означает готовый пользовательский
workflow запроса возврата: требуется сохранённый запрос, результат провайдера,
повтор и сверка. Возврат последнего subscription order отзывает его доступ;
возврат старого периода не должен отзывать более новый оплаченный период.

Booking `POST /admin/refunds` проверяет второго admin ID, но пока не хранит
отдельного действия подтверждения этим администратором. Называть это завершённым
four-eyes approval нельзя. Кроме того, текущий маршрут устанавливает refunded /
partially_refunded по `outcome.kind`, не ожидая асинхронного `outcome.status`.
Перед live нужны отдельное подтверждение второго оператора и отражение pending /
failed / succeeded возврата; принятый PSP запрос не равен завершённому возврату.
Нельзя регистрировать асинхронный live refund adapter, сохранив этот маршрут без
изменений. Stub-результат не подтверждает реальную выплату.

### Автопродление

Для каждого provider billing cycle нужен отдельный BillingOrder с сохранённой
ценой периода и стабильным идентификатором цикла. Сегодня повтор create order
по действующему тому же тарифу отклоняется, а `_activate_subscription` начинает
период от момента обработки paid. Поэтому `create_subscription` и
`subscription_reference` ещё не составляют полный renewal workflow.

До подключения автосписаний требуется явная обработка cycle success/failure,
поздней доставки, повторов, paid-at boundaries, past_due и прекращения будущих
списаний. Нельзя продлевать текущую подписку повторной доставкой старого paid
или выдавать новый период без отдельного заказа. Определение начал/концов
периодов и применяемой версии цены должно быть согласовано с партнёром и
записано в заказ, а не вычисляться заново после задержанного webhook.

### Настройки и фактический live switch

Дополнительно к перечисленным выше env обязательны:

- `BOOKER_PAYMENT_ALLOW_STUB=false` в production;
- `BOOKER_COMMERCE_ALLOW_STUB=false` в production;
- `BOOKER_ALLOW_DEFAULT_WEBHOOK_SECRET=false` и непубличный booking webhook key;
- отдельные секреты sandbox/production и раздельные booking/commerce endpoints;
- актуальная конфигурация `BOOKER_REQUIRE_ADMIN_2FA_ENFORCED` для операторских
  действий, вместе с настройкой и проверкой TOTP пользователей.

Merchant/public/secret key и юридические поля в Settings — точки конфигурации,
не доказательство их проверки live-кодом. Сейчас `payment_live_enabled()` всегда
false, неизвестный commerce provider возвращает DisabledProvider, а
`LivePaymentAdapter` отклоняет вызовы. Готового переключателя «внести секреты и
включить live» ещё нет. Регистрация адаптера и проверяемый production opt-in
должны сопровождаться отрицательными тестами: отсутствие любого обязательного
секрета/юридического допуска не включает платежи и не включает stub fallback.

### Локальная проверка и доказательства при передаче

Из `apps/api` на отдельной тестовой БД:

```bash
BOOKER_ENVIRONMENT=test BOOKER_DATABASE_URL=sqlite:// ../../.venv/bin/python -m pytest \
  tests/test_payment_adapter.py tests/test_payment_guards.py tests/test_payments.py \
  tests/test_external_payment_confirm.py tests/test_commerce.py -q
```

Этот набор проверяет текущие адаптеры/доменные ограничения. Он не заменяет
sandbox acceptance PSP. К результату интеграции необходимо приложить:

1. Версию адаптера и конфигурацию без значений секретов, merchant sandbox ID,
   описание подписи и соответствие событий доменным статусам.
2. Примеры provider event IDs, booking/order IDs, payload hashes и результаты
   duplicate/out-of-order/mismatch/timeout тестов; raw secrets не прикладывать.
3. Результат сверки статуса после неопределённого сетевого ответа без повторного
   списания, а также подтверждённый full/partial refund по утверждённой модели.
4. Renewal cycle fixtures и подтверждение, что повтор/поздняя доставка не создаёт
   второй период, не меняет сохранённую цену и не отменяет новый период старым refund.
5. PostgreSQL гонки capture с отменой/истечением/чужим резервом; invoice/capture
   не обещают дату, если возврат webhook сообщает reservation conflict.
6. Отрицательные production-gate тесты и протокол отдельного допуска к запуску.

Приоритет ближайшей работы: захват/отмена даты, устойчивый checkout receipt,
подлинное подтверждение refund, renewal mapping. До устранения этих пробелов
раздел 34 мастер-задания не считается выполненным.
