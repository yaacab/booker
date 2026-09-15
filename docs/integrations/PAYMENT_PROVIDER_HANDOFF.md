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
Booking refunds имеют сохранённый запрос, отдельное подтверждение вторым
администратором и состояния исполнения; см. протокол ниже.

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
- `verify_webhook(event_id, payment_id, status, signature)` — только legacy stub.
- `verify_raw_webhook(payload: bytes, headers: dict)` проверяет исходную подпись
  и возвращает `VerifiedPaymentEvent(event_id, payment_id, status, amount_rub,
  currency, merchant_id, provider_reference)`.
- `merchant_id` — ожидаемый получатель из конфигурации адаптера; default берётся
  из BOOKER_PAYMENT_MERCHANT_ID. Его нельзя брать из входящего уведомления.
- `get_payment_status(payment_id, provider_reference, idempotency_key)` —
  authenticated read → VerifiedPaymentEvent, без создания нового checkout.
  Если reference потерян, адаптер ищет исходный платёж по сохранённому ключу /
  metadata. Возвращаются фактические реквизиты партнёра, не эхо аргументов.
- `normalize_idempotency_key(key)` нормализует ключ до booking scope.
- `refund(payment_id, amount_rub, total_rub, idempotency_key)` возвращает
  `RefundOutcome(refund_id, amount_rub, kind, status)`.
- `LedgerHooks.on_session_created/on_capture/on_refund` — интерфейс событий;
  `NoOpLedgerHooks` не является бухгалтерским регистром или банковской сверкой.

Endpoint провайдера — `POST /payments/provider-webhook`. Он передаёт адаптеру
исходные байты и headers, ограничивает body 64 KiB и не пишет сырой payload или
подпись в журнал. Адаптер проверяет алгоритм подписи/временную метку партнёра до
нормализации. Сервер затем проверяет merchant, RUB, точную integer amount_rub,
payment ID и provider_reference. Части рубля нельзя округлять молча: до изменения
денежного контракта адаптер обязан их отклонять.

Нормализованные pending/succeeded/failed применяются под теми же блокировками,
что capture/cancel/refunds. Первое проверенное уведомление может связать reference
с уже сохранённым Payment, если ответ создания checkout был потерян. UNIQUE
(provider, provider_reference) не позволяет одному платежу PSP оплатить две
внутренние записи. Ограничение действует также при сохранении checkout receipt;
ошибочный повтор reference оставляет сессию uncertain без чужого URL.

Receipt ID — SHA-256 scope provider + event ID. В PaymentWebhookEvent хранится
fingerprint финансовых полей; повтор того же нормализованного события возвращает
сохранённый ответ, изменение полей — 409. Повторная доставка с другим форматированием
JSON допустима, если проверена подпись именно новых исходных байтов. ID события
резервируется в транзакции до capture/ledger hook. Обработка синхронной БД вынесена
из async event loop в threadpool. Миграция `f9a0b1c2d3e4` добавляет fingerprint и
уникальный индекс references; существующие данные с дубликатами нельзя молча
переписывать, их необходимо сверить до применения миграции.

`POST /payments/webhook` с signature в JSON теперь отклоняет **все не-stub**
адаптеры. Нельзя подключать настоящий PSP через этот устаревший формат. Для
локальных acceptance tests StubPaymentAdapter умеет HMAC-SHA256 исходного body
в header `X-Booker-Signature`; merchant — фиксированный stub-merchant. Это не
сигнатурный протокол реального PSP и не разрешение включать stub в production.
Factory и production-gates остаются fail-closed; реальный партнёр не выбирался.

`POST /bookings/{booking_id}/payments` возвращает id/status/amount/provider,
session_state и checkout_url. Payment хранит checkout_url и provider_reference;
миграция `d7e8f9a0b1c2` помечает исторические платежи ready, не создавая им новую
сессию. Новый Payment со state=creating и ключом сохраняется **до** внешнего вызова.
Тайм-аут/ошибка адаптера сохраняет uncertain без секретного текста ошибки. Повтор
с любым новым UI-ключом использует сохранённые payment_id/amount/idempotency_key.
После ready внешний вызов не повторяется. На PostgreSQL два одновременных checkout
проверены отдельными соединениями: один вызов партнёра, один сохранённый результат.

Адаптер обязан обеспечивать идемпотентность `create_session` на стороне PSP и
возвращать ту же сессию по тому же ключу после неопределённого ответа. Возвращается
pending; succeeded в ответе создания сессии не является подтверждением capture и
отклоняется. Нужны ограниченные сетевые тайм-ауты адаптера; запрос выполняется под
блокировкой события. Проверяются provider/payment ID, HTTPS URL без credentials
и provider_reference. В audit не попадают bearer URL/тело ошибки. Ссылка доступна
только writer заказчика при действующем резерве, ожидающей оплате и включённом
исходном провайдере; Deal Room показывает отдельное действие «Перейти к оплате».

Это сохранение и восстановление checkout, не банковская сверка: если uncertain
платёж уже потерял резерв/событие закрыто, повтор create_session отклоняется.
Реальный адаптер должен уметь сверять такую сессию без создания новой (status API /
проверенное входящее событие), а также ограничивать срок действия checkout. Общий вход
raw webhook реализован выше; активная сверка статуса описана ниже.

### Сверка состояния существующего booking payment

`POST /admin/payments/{id}/reconcile` — platform admin с обязательно настроенным
TOTP и свежим кодом. Body содержит только totp. Endpoint не принимает от оператора
статус/сумму/результат и не вызывает create_session. Перед запросом фиксируется
payment.reconciliation_requested и коммитится транзакция: ожидание сети не держит
Event/resource/payment locks. Адаптер читает исходный provider_reference или
creation idempotency key. Его отсутствие/неподдерживаемая сверка — 503; транспортная
неопределённость — 502 без тела ошибки партнёра и без изменения денежного статуса.

Ответ проверяется по payment ID, merchant, RUB, точной сумме и reference. Далее
`apply_verified_payment_event` получает свежие domain locks, reread и те же
ограничения capture, что raw webhook. Для lookup используется отдельный namespace
receipt и fingerprint финансовых данных: одинаковые результаты не выполняют
capture повторно, изменение provider status получает отдельный receipt. После
обработки endpoint возвращает текущее состояние Payment/Booking, а не старый
ответ receipt. Поэтому повтор pending после уже обработанного capture не скрывает
сохранённую оплату и отмечает расхождение оператору. Статус частичного/полного
возврата не перезаписывается capture lookup; возвраты сверяются отдельно.

При позднем succeeded после отмены/истечения сохраняется денежный факт и
reservation conflict, дата не восстанавливается. PostgreSQL interleaving test
доказывает, что отмена завершается во время ожидания ответа партнёра, а дальнейшая
сверка не отменяет эту отмену. Оператор видит в `/admin` сумму из API, состояние
партнёра и Букера, флаг необходимости проверки и ссылку на сделку. Неопределённость
создания checkout не показывается в Deal Room как ожидание счёта после capture.

Local stub не имитирует независимую банковскую сверку: get_payment_status по
умолчанию fail-closed. Успешные/ошибочные ответы этого внешнего read interface
проверены fixtures адаптера в API/PG tests; UI provider-response fixtures отдельно
помечены. Реальный адаптер должен реализовать authenticated status lookup с
ограниченными тайм-аутами. External-перевод не направляется в этот метод и остаётся
в отдельном ручном подтверждении оператора.

Capture использует Event → resource → slot → Payment; отмена и истечение
резерва начинают с того же Event/resource/slot. После ожидания expire_holds
перечитывает hold и не освобождает уже consumed резерв. Четыре теста на отдельных
соединениях PostgreSQL проверяют capture/cancel и capture/expiry в обоих порядках.
Capture проверяет открытое событие, собственный действующий hold, будущее окно,
согласованный quote и совпадение суммы; при конфликте сохраняет Succeeded и
payment.reservation_conflict без подтверждения даты. Новый checkout закрытого
события запрещён; повтор сохранённого платежа возвращает прежний результат.
Это прикладной протокол блокировок, не защита от произвольных прямых SQL-записей.

### Возвраты и подтверждения операторов

Commerce нормализует **полный** возврат в `ProviderEvent.status=refunded` с суммой
исходного заказа. Это не поддержка произвольного partial refund. Наличие метода
`CommerceProvider.refund` само по себе не означает готовый пользовательский
workflow запроса возврата: требуется сохранённый запрос, результат провайдера,
повтор и сверка. Возврат последнего subscription order отзывает его доступ;
возврат старого периода не должен отзывать более новый оплаченный период.

Booking возвраты хранятся в `PaymentRefund` (миграция `e8f9a0b1c2d3`).
`POST /admin/refunds` принимает payment_id, optional amount_rub (пусто — остаток),
reason и idempotency_key. Он создаёт awaiting_approval и не вызывает партнёра.
`POST /admin/refunds/{id}/approve` вызывается **другим** platform admin под его
сессией с обязательным настроенным TOTP и свежим кодом. Оба actor ID, сумма,
основание и время подтверждения сохранены. Перед вызовом проверяются текущие
полномочия обоих участников; старый approver_user_id в теле не принимается.

Статусы: awaiting_approval → approved → submitting → pending / uncertain /
succeeded / failed. До отправки можно reject; повтор отклонённого запроса не
запускает возврат. Запрос и ключ коммитятся до внешнего вызова. `retry` использует
прежний ключ; `refresh` только читает статус pending через
`PaymentAdapter.get_refund_status(payment_id, refund_id, amount_rub, total_rub,
idempotency_key)`. `refund` обязан быть идемпотентным у PSP; get_refund_status не
создаёт перевод. Для сетевой неопределённости нельзя возвращать failed.
Партнёрские succeeded/failed — терминальные результаты; противоречивый результат
не перезаписывает завершённую запись и требует сверки. Проверяются сумма, kind и
неизменность provider reference; UNIQUE(provider, provider_reference) запрещает
учесть один перевод дважды, в том числе для разных платежей. Savepoint откатывает
ложное начисление/audit при конфликте. Сырой текст ошибки не раскрывается пользователю.

Только succeeded меняет Payment: сумма успешных возвратов определяет
partially_refunded/refunded. Pending/failed/uncertain не выдают платёж за
возвращённый. Незавершённый запрос резервирует остаток: новый запрос на этот
платёж запрещён до завершения. Успешные частичные возвраты суммируются сервером;
превысить исходный платёж нельзя. Исторический partially_refunded без записанной
суммы не получает выдуманный остаток и требует отдельной сверки оператора.
Все mutations используют Event/resource/slot/Payment locks. PostgreSQL тесты
проверяют две одновременные approve и создание второго возврата во время первого.

В режиме external approve оставляет pending. Только отдельный
`POST /admin/refunds/{id}/confirm-external` с номером проверенного перевода и
TOTP фиксирует явное утверждение оператора о фактическом перечислении. Это не
банковский webhook. Stub использует стабильный refund reference и всегда
помечен как тест без выплаты денег. UI `/admin/refunds`: очередь/фильтр/пагинация,
создание, второе подтверждение, отклонение, повтор, сверка и external confirmation.
`GET /admin/refunds` доступен только admin и ограничивает размер/частоту запросов.

Точка нормализации результата: `routers/refunds.py:save_outcome` (вызывает
apply_outcome внутри savepoint) под блокировкой
платёжного контекста. Перед вызовом из будущего webhook необходимо проверить
исходную подпись, merchant, provider/payment/refund binding, сумму и валюту.
Публичный неподписанный endpoint изменения результата отсутствует. Проверка
реального PSP и raw refund webhook ещё не выполнены; generic status-method
предоставляет интеграционную границу и тестируется адаптером на границе провайдера.

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
  tests/test_external_payment_confirm.py tests/test_provider_webhook.py tests/test_payment_reconciliation.py tests/test_refunds.py tests/test_commerce.py -q
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

Приоритет ближайшей работы: raw refund mapping,
commerce refund workflow, renewal mapping. До устранения этих пробелов
раздел 34 мастер-задания не считается выполненным.
