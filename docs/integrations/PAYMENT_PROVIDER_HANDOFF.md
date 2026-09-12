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
Booking refunds сохраняют существующий four-eyes и audit процесс.

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
