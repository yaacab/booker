# Букер — состояние проекта и handoff

> **Актуальная общая готовность полного запуска: 55,00% на 02.10.2026.** Фиксированный реестр результатов и оставшихся 45,00 п.п.: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md). S05 закрыт локально (+3,00 п.п.); упоминания 84% ниже — исторические оценки локальной серии до пересчёта.

> **Отдельные шкалы на том же срезе:** технический MVP 46,00% (осталось 54,00 п.п.); красивый сайт с дизайном 15,00% (осталось 85,00 п.п.). Критерии и формула всех трёх шкал — в [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md). Эти проценты не складываются.

> **Текущая рабочая цель:** [технический MVP](DEVELOPMENT_GOAL.md). Право, реальные платежи, финансы и новый дизайн отложены; дизайн ведётся отдельным проектом. Исторические разделы ниже описывают полный продукт, а не текущую очередь разработки. Перед новым срезом сверять цель, состояние Git и затронутые зависимости.

## Локальный интеграционный кандидат — 02.10.2026

- Текущий HEAD `fbb41f5c3d12a1de5368121c95af3ec6bc6f5da7`, ветка `feat/sitewide-lime-design`. Общий dirty tree сохранён; основной Git index не затронут. Экспортированный кандидат в `/tmp/booker-integration-candidate-v2` совпадает с рабочим деревом, кроме шести E2E-файлов, которые затем перенесены в экспорт для повторного прогона. В отдельном временном index подготовлен состав из 390 изменённых файлов без `outputs/`, `.next-*`, БД и токенов.
- Первый полный browser E2E: 76 PASS/4 FAIL. Исправлены неоднозначный селектор подтверждения условий, ожидание устаревшей фразы оферты и повторное использование отозванного админского токена. Повторная проверка затронутых файлов: 9 PASS.
- Второй полный browser E2E выявил, что recovery-тест требует отдельную БД и меняет TOTP администратора; навигация кабинетов и отрисовка 300 исследовательских карточек иногда выходили за короткие ожидания dev-сервера. Recovery теперь запускается только с явным флагом изоляции; ожидания маршрутов увеличены без изменения приложения.
- Итоговая локальная проверка: полный browser E2E **78 PASS/2 SKIP** на временной SQLite; отдельный recovery E2E **1 PASS** на другой временной SQLite. До этих шести E2E-правок на том же коде API **725 PASS/9 SKIP**, web unit **72 PASS**, TypeScript и Next build PASS. После правок TypeScript, `git diff --check` и source/deploy-payload secret gate PASS. Изменения после API/web build затрагивают только E2E-тесты.
- Staging, PostgreSQL и production этим локальным прогоном не подтверждены. P08/O04/T08 остаются открытыми, оценки 55,00% / 46,00% / 15,00% не меняются.
- Draft PR [#18](https://github.com/yaacab/booker/pull/18) создан на `c64646889c5a151c447baa674a69a89805f80493`. Первый CI: secret-source, dependency-audit и web PASS; API и e2e-critical FAIL. Причины подтверждены: sealed backup использовал системный Python без объявленной зависимости `cryptography`; E08 читал Deal Room до завершения UI-запроса hold. В следующем срезе добавлены зафиксированные зависимости и общий Python для backup/restore, а E08 ждёт HTTP 200 и реальный таймер hold. Адресные проверки: backup/schema 22 PASS/2 SKIP, E08 1 PASS. Повторный CI на новом SHA требуется; оценка не меняется.

Дата фиксации: **2026-10-01**. Этот файл предназначен для продолжения работы в новом чате. Перед любыми изменениями новый агент обязан сопоставить его с фактическими `git status`, `git diff` и тестами. Репозиторий остаётся источником истины.

## 1. С чего начать в новом чате

1. Прочитать `AGENTS.md`, `docs/product/CONTRACT.md`, этот файл и только затем профильные планы.
2. Выполнить:

   ```bash
   cd /home/art67/booker
   git status --short --branch
   git rev-parse HEAD
   git diff --check
   ```

3. **Не** выполнять `git reset`, `git clean`, force checkout, rebase или массовое `git add -A`. Рабочее дерево содержит большой объём незакоммиченной проектной работы и файл `:memory:.ses`, который нужно оставить нетронутым.
4. Не переделывать уже реализованные вертикали без подтверждённой ошибки. Сначала запускать узкий тест, затем полный набор затронутого приложения.
5. Законченную и проверенную часть работы при необходимости самостоятельно фиксировать отдельным коммитом с точным составом файлов. Для GitHub CI открыть/обновить обозримый PR к `main`/`master`: push в feature-ветку без PR не запускает текущий workflow. Пока идут проверки, продолжать независимую работу; затем проверить результат на точном SHA. Не включать соседний dirty diff, секреты и временные файлы. Развёртывание согласовывать отдельно.

## 2. Git и рабочее дерево

- Репозиторий: `/home/art67/booker`.
- Ветка: `feat/sitewide-lime-design`.
- HEAD на момент фиксации: `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907` (`feat: add moderated venue catalog lifecycle`).
- Ветка опережает `origin/feat/sitewide-lime-design` на один коммит.
- Рабочее дерево намеренно грязное: на 01.10 после security/SLA-среза `git status --short` показал 190 изменённых или неотслеживаемых путей. Это счётчик всего дерева, не только данного среза; перед работой пересчитать заново.
- Все изменения текущей большой серии находятся поверх указанного HEAD. Нельзя считать их отдельными независимыми патчами без просмотра diff.
- `git diff --check` проходит.
- Неотслеживаемый `:memory:.ses` не относится к продукту; не удалять и не добавлять в коммит.

## 3. Продуктовые источники и запреты

Порядок приоритета:

1. `AGENTS.md`.
2. `docs/product/CONTRACT.md`.
3. Этот handoff и подтверждённое состояние кода.
4. Профильные планы и аудиты в `docs/product`, `docs/design`, `docs/ops`.

Неподвижные правила:

- Бренд **Букер**, репозиторий `booker`; не смешивать с THE AIV.
- Канонический домен `bukergo.ru`; `bookergo.ru` и `bukergo.online` должны быть редиректами. См. `docs/ops/DOMAINS.md`.
- Цена, комиссия, график платежей и возврат рассчитываются и подтверждаются API. Клиент не вычисляет деньги.
- Live acquiring запрещён до письменного гейта юриста и партнёра. До него разрешён честный `external-payment` или stub-контур.
- AI не решает споры и не создаёт юридически значимый оффер.
- Не обещать Protect/страхование.
- Визуальная реализация проходит отдельное согласование. Не интегрировать новый дизайн или анимацию до явного утверждения владельца.
- Публичная страница индексируется только при выполнении серверного predicate публикации.
- Подтверждение сборки или HTTP 200 не заменяет проверку авторизованного пользовательского сценария.

## 4. Архитектура

### API

- Python 3.11+, FastAPI, SQLAlchemy 2, Alembic.
- Код: `apps/api/booker_api`.
- Роутеры: `apps/api/booker_api/routers` (`admin`, `analytics`, `briefs`, `catalog`, `deals`, `favorites`, `health`, `identity`, `payments`, `promo`, `reviews`, `saved_searches`, `services`, `shortlists`, `trust`, `venue_admin`).
- Модели: `apps/api/booker_api/models.py`.
- Runtime-адаптация SQLite: `apps/api/booker_api/db.py`.
- Миграции: `apps/api/alembic/versions`.
- Тесты: `apps/api/tests`.
- Проектное окружение: `apps/api/.venv`; команды запускать через `.venv/bin/python -m ...`.
- Production путь рассчитан на Alembic/PostgreSQL; малый concierge-контур и тесты используют SQLite. Оба пути должны оставаться совместимыми.

### Web

- Next.js 15, React 19, TypeScript.
- App Router: `apps/web/app`.
- Общие компоненты: `apps/web/components`.
- API-клиент и утилиты: `apps/web/lib`.
- Playwright: `apps/web/e2e`.
- Основные пространства: публичный discovery, Event Studio/Control Room, Deal Room, кабинеты customer/artist/venue, сообщения, support и admin.

### Инфраструктура и документы

- Backup/deploy/restore: `infra/`.
- Product truth и планы: `docs/product/`.
- Figma/motion/route atlas: `docs/design/`.
- Операционные доказательства: `docs/ops/`.
- Юридические документы остаются черновиками: `docs/legal/`.

## 5. Реализованные вертикали

Ниже перечислено то, что уже находится в рабочем дереве и было проверено тестами до или во время этой фиксации.

### Поддержка

- Изолированные support tickets, сообщения пользователя, внутренние заметки оператора, idempotency и CAS-переходы.
- Сессии помощника поддержки, exchanges, feedback, эскалация человеку и SLA.
- Основные файлы: `booker_api/support_agent.py`, support части `routers/trust.py` и `routers/admin.py`, страницы `apps/web/app/support`.
- Миграции: `e8b9...`, `e9c0...`, `ea1d...`.
- Browser E2E поддержки был пройден ранее.
- Повторная локальная проверка 01.10: support/security 18 PASS после исправления маскирования `API key is …` и feedback comment; отдельный support Playwright 1 PASS, web unit 11 PASS, TypeScript/build/Ruff PASS. История обращения и feedback больше не сохраняют этот проверенный формат секрета открытым текстом.
- CAS-гейты закрыты локально: интерливинг сообщения после handoff и stale close из второй вкладки воспроизведены красными тестами, затем стали зелёными. Close/reopen требуют точный `If-Match` с `state_version`; повтор с устаревшей версией получает 409. Рабочий SLA-календарь включается только явной конфигурацией, без неё публичный срок отсутствует; просрочка и факт позднего первого ответа видны в защищённой admin queue. Миграции `e8b9`/`e9c0` проверяют ограничения при adoption, а `e8b9` чинит недостающие ticket-ограничения пилотной SQLite. Полный API 315 PASS, web unit 11 PASS, TypeScript/build, Ruff и support browser E2E 1 PASS.
- Общий график поддержки согласован: ежедневно 10:00–22:00 МСК; праздничные дни и адресный маршрут просрочки ещё не решены, поэтому публичный срок остаётся выключенным. После handoff web предлагает отдельную новую сессию помощника, сохраняет человеческое обращение и показывает оценку ответа после reload; указатель сессии в браузере разделён по user ID и org ID. API отдаёт сохранённый feedback сессии, отклоняет чужой доступ и повторно принимает идентичную оценку; оценка после handoff не меняет статус/версию тикета. Проверка: полный API 315 PASS, целевой API 1 PASS после дополнительного assert, web unit 11 PASS, TypeScript/build/Ruff/diff-check PASS, support Playwright 1 PASS на временной SQLite (keyboard feedback, чужой POST 404, replay, reload, mobile новая сессия, сохранённый тикет). Открытые гейты: PostgreSQL-конкурентность, миграция на копии реальной непустой БД (локальный тест с одной записью PASS), production E2E и реальный операторский маршрут. Подробнее — `docs/ops/IMPLEMENTATION_AUDIT_2026-09-30.md` и `docs/ops/SLA.md`.
- Для PostgreSQL добавлен отдельный opt-in integration harness с жёстким guard тестового loopback DSN, уникальной schema и очисткой. На этой машине нет `TEST_POSTGRES_DSN` и локального PostgreSQL: 7 guard-тестов PASS, 4 интеграционных сценария SKIP, PG-подтверждения нет. Read-only проверка нашла capture без `provider_reference`, который выпадал из сверки; теперь создаётся discrepancy и payout fail-closed. Полный локальный API suite до последнего PG-сценария: 323 PASS, 3 SKIP; отдельный тест прямого payout guard после полного прогона 1 PASS; финальный узкий набор 9 PASS, 4 SKIP; Ruff, compileall, diff-check PASS. Внешний PostgreSQL gate остаётся открытым. См. `docs/ops/IMPLEMENTATION_AUDIT_2026-09-30.md`.
- Локальный backup/restore drill на синтетической SQLite из `/tmp` прошёл на финальном скрипте: tenant, support, payment metadata и upload восстановлены, `integrity_check=ok`, архив и каталоги имели `0600/0700`, backup+restore заняли 0.284 с (не production RTO). Четыре новых теста воспроизвели пять дефектов до исправления: partial restore после поздней ошибки, перезапись архива за ту же секунду, частичный архив при сбое, удаление retention в dry-run и остановка API по умолчанию. После исправления профильный набор 11 PASS; полный API suite после функциональных правок 330 PASS, 4 SKIP (PG без DSN), финальная shell-публикация отдельно проверена профильным набором. Проверки архива, cleanup и opt-in restart включены. Архив не зашифрован, manifest внутри архива не является подписью. Production/staging restore, PostgreSQL restore, общий snapshot DB+uploads и шифрование off-site остаются открытыми. Подробнее — `docs/ops/RESTORE_DRILL_LOG.md` и `docs/ops/IMPLEMENTATION_AUDIT_2026-09-30.md`.

### Споры

- Dispute case management, evidence, SLA, защищённые решения и admin queue.
- Основной модуль: `booker_api/disputes.py`.
- Миграция: `ec3f4a5b6c7d_dispute_case_management.py`.
- AI не принимает решение по спору.

### Деньги до текущей сверки

- `PaymentObligation` разделяет аванс, остаток и другие обязанности.
- Append-only `MoneyMovement` является денежным ledger для capture/refund.
- Защиты от конкурентных дубликатов платежа, capture и refund.
- Refund request требует независимого согласования там, где это предусмотрено.
- External transfer reports отделены от provider capture.
- Offer version хранит неизменяемый `payment_terms_json`.
- Обязательства имеют `due_at`, `grace_until`, `required_before_check_in` и вычисляемые состояния `pending/due/overdue/satisfied/not_applicable`.
- Неполные legacy-графики fail closed с `review_required`.
- Неоплаченное обязательство `required_before_check_in` блокирует check-in независимо от grace.
- Сроки нормализуются в UTC.
- Порядок блокировок унифицирован как Event → Booking; запросы сортируются, чтобы снизить риск deadlock.
- Admin TOTP endpoint запуска напоминаний: `/admin/payment-reminders/run`.
- Outbox enqueue использует nested transaction для обработки конкурентного unique collision.
- Миграции цепочки: `a3c4...`, `b4d5...`, `c5e6...`, `f1a2...`, `f38f...`.

### Оффер, договор и коммуникация

- Request-stage conversation начинается до создания booking.
- Монотонные sequence/unread позиции.
- Snapshot организаций участников защищает историю от последующих изменений членства.
- Offer acknowledgements и contract signatures append-only, с acting organization.
- Сообщения сохраняют actor attribution; read state разделён по организации.
- Миграции: `e7a8...`, `ed4a...`, `ef5b...`, `f05c...`, `f16d...`, `f27e...`.

### Публикация и SEO

- Единый server-side predicate публикационной готовности supply.
- Проверяются цена, календарь не менее 30 дней, медиа, представитель, верификация и подтверждающие evidence.
- SEO/canonical/noindex/sitemap связаны с публикационной готовностью.
- Основной модуль: `booker_api/publication_eligibility.py`.
- Web: `apps/web/app/robots.ts`, `sitemap.ts`, `middleware.ts`, `apps/web/lib/seo.ts`.
- Миграция evidence: `eb2e3f4a5b6c_supply_publication_evidence.py`.

### Готовность события

- `booker_api/event_readiness.py` вычисляет readiness по обязательному составу.
- Учитываются только связанные booking в статусах confirmed/in-progress/completed.
- Незаполненная обязательная позиция блокирует готовность и check-in; необязательная позиция не блокирует.
- Readiness возвращается сервером в event/detail/offline/UI.

### Безопасность и права

- Продолжена object-level авторизация по ролям и организациям.
- Admin действия используют TOTP там, где они критичны.
- Вложения имеют quarantine до проверки.
- Не считать весь authz доказанным только из-за полного unit/integration набора; реальные multi-role браузерные сценарии остаются отдельным gate.

## 6. Текущий завершённый срез: provider-neutral reconciliation core

Срез добавлен 2026-10-01. Он создаёт нейтральное ядро двусторонней сверки без подключения live-партнёра.

### Изменения модели

- `Payment.provider_merchant` сохраняет merchant snapshot, а `Payment.provider_reference` защищён частичным уникальным индексом `(provider, provider_merchant, provider_reference)` для ненулевых значений.
- `Booking.payout_blocked` и `Booking.payout_block_reason`.
- `ReconciliationRun`: identity отчёта, период, hash содержимого, статус и причина ошибки.
- `ReconciliationEntry`: неизменяемые строки партнёрского реестра.
- `ReconciliationDiscrepancy`: тип расхождения, связи с booking/payment/movement/entry, статус и ручное resolution.
- Миграция: `apps/api/alembic/versions/f49a012bc3d4_payment_reconciliation.py`.
- Runtime SQLite adoption и triggers: `apps/api/booker_api/db.py`.

### Поведение ядра

- Файл: `apps/api/booker_api/reconciliation.py`.
- Режимы `external` и `disabled` исключены из партнёрской сверки.
- Входной отчёт нормализуется, даты обязаны иметь timezone, период проверяется.
- Один и тот же `report_id` с тем же hash идемпотентен.
- Один `report_id` с другим содержимым создаёт `report_hash_conflict` и переводит run в failed.
- То же содержимое под другим `report_id` распознаётся как идемпотентный replay.
- Неполный отчёт сохраняет failed run без entries, создаёт глобальное `incomplete_report` discrepancy и блокирует выплаты до ручного разбора; успешным checkpoint не считается.
- Сверка идёт partner → ledger и ledger → partner.
- Обе стороны сверки изолированы по `(provider, merchant)`; реестр одного merchant не видит движения другого.
- Выявляются duplicate provider operation, missing in ledger, missing at provider, amount/currency/status mismatch.
- Несколько частичных refund сопоставляются с отдельными движениями один к одному, включая сумму и валюту.
- `provider_operation_id` нельзя повторно использовать в другом отчёте того же provider/merchant; защита есть в сервисе и unique constraint.
- Legacy-платежи без merchant snapshot не пропускаются молча: они создают `legacy_merchant_unassigned` и блокируют связанную выплату до ручного разбора.
- Расхождение, связанное с booking, включает payout block.
- Глобальное расхождение без известного booking консервативно блокирует известные booking этого provider/merchant.
- Сверка никогда не исправляет и не мутирует `MoneyMovement`.
- Ручное resolution снимает payout block только когда для booking не осталось других открытых расхождений.
- Импорт и создание discrepancy обрабатывают unique race через savepoint и возвращают идемпотентный результат победившего запуска; merchant booking блокируются в одном сортированном порядке.
- Identity полей run и discrepancy защищена ORM и DB triggers; run/discrepancy/entry нельзя удалять, изменяемыми остаются только операционные status/resolution поля.
- Payment session сохраняет `provider_reference`, возвращённый adapter.
- SQLite и PostgreSQL миграционные пути защищают reconciliation entries от update/delete; runtime SQLite создаёт те же triggers.
- Миграция умеет принять schema, ранее созданную runtime `Base.metadata.create_all`, не падая на повторных колонках и таблицах.

### Проверки этого среза

Выполнены 2026-10-01:

```text
Ruff по reconciliation/models/db/payments/migration/tests: PASS
tests/test_reconciliation.py: 13 passed, 1 warning
tests/test_alembic.py: 15 passed, 4 warnings
tests/test_payments.py + tests/test_payment_adapter.py: 23 passed, 1 warning
полный apps/api pytest: 290 passed, 4 warnings, 59.92s
git diff --check: PASS
```

Предупреждения известные и неблокирующие: Starlette `httpx` deprecation и Python 3.12 sqlite datetime adapter deprecation.

Независимый read-only reviewer трижды проверил reconciliation diff. Найденные P1 по merchant isolation, payout-block semantics, partial refunds, конкурентности, lock ordering и immutable audit были исправлены; финальный повторный review сообщил, что оставшихся P0/P1 в этом срезе нет.

## 7. Что в reconciliation ещё не реализовано

Обновление 2026-10-01: admin-вертикаль API теперь реализована в текущем незакоммиченном дереве. Маршруты `/admin/reconciliation/runs` (POST/GET), `/admin/reconciliation/discrepancies` (GET), `/admin/reconciliation/discrepancies/{id}` (GET) и `/admin/reconciliation/discrepancies/{id}/resolve` (POST) требуют admin и TOTP. Импорт использует строгие поля, лимит 500 строк и 512 КБ; закрытие сохраняет основание и audit. Новое расхождение ставит идемпотентное P0 письмо в outbox без содержимого реестра. Исправлены сохранение payout block при сверке другого merchant и повторный открытый сигнал после уже закрытого конфликта hash. Список исключений не раскрывает `details_json`; детальный просмотр доступен только админу с TOTP.

Проверка после admin-вертикали: узкий reconciliation набор **18 passed**, полный API **295 passed, 4 warnings**, Alembic **15 passed, 4 warnings**, `git diff --check` PASS. HEAD остаётся `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`; коммита/пуша/деплоя не было. Запуск тестов потребовал локального разрешения sandbox для stream fd.

Следующий локальный backend-срез: `booker_api/payout_eligibility.py` добавляет переиспользуемый fail-closed guard для будущего транзакционного payout claim. Он отклоняет `stub/external/disabled`, отсутствующий capture, денежное движение вне покрытого периода, открытое прямое или глобальное расхождение, materialized payout block и отсутствие полного checkpoint для каждой пары provider/merchant. Реального payout endpoint или вызова провайдера нет; legal/partner gate остаётся обязательным. Добавлены тесты guard и SQLite миграционный roundtrip `f38 → f49 → f38 → f49` с проверкой DB triggers. Независимый read-only review выявил и помог исправить пропуск direct discrepancy после смены merchant, принятие stub и непокрытое движение.

Финальные локальные проверки backend-среза: узкий reconciliation/payout/Alembic набор **40 passed, 4 warnings**; полный `apps/api` pytest **302 passed, 4 warnings**; Ruff и `git diff --check` PASS (2026-10-01). Текущая ветка и HEAD не менялись.

**PostgreSQL proof не выполнен:** в текущей локальной среде нет `psql`, `postgres`, `pg_ctl`, `initdb`, Docker или Podman. Проверка `FOR UPDATE`, конкурентных savepoint/import, PostgreSQL trigger/downgrade и времени блокировки DDL требует отдельной временной PostgreSQL БД. SQLite roundtrip не является доказательством поведения PostgreSQL. До реального payout нужен транзакционный идемпотентный claim, удерживающий блокировку до безопасного перехода к провайдеру; guard сам не создаёт claim и не разрешает выплату. На копии PostgreSQL БД нужно проверить дубликаты `provider_reference` перед уникальным индексом и оценить DDL lock time.

Открытые пункты:

1. Подключить `assert_payout_eligible` внутри будущего атомарного payout claim только после legal/partner gate; функция сама не совершает выплату. Неполный реестр создаёт глобальное расхождение и payout block. Отсутствие отчёта за требуемый период также блокирует guard.
2. Запустить добавленный opt-in PostgreSQL integration набор на выделенной локальной тестовой БД и проверить миграции, triggers, конкурентный импорт и SQL CAS. Текущие фактически запущенные автоматические тесты работают на SQLite; гонка нового платежа с пересчётом блока и параллельные API-запросы поддержки остаются отдельными проверками.
3. Уточнить период ledger: сейчас используется `MoneyMovement.created_at`; реальному адаптеру может понадобиться provider occurrence timestamp.
4. Добавить operator admin UI для payment exceptions после отдельного утверждения визуального дизайна.
5. Подключать конкретный формат партнёра только после выбора партнёра; нейтральное ядро не должно знать CSV/JSON конкретного провайдера.
6. Live capture/refund/payout и реальные registry E2E остаются запрещены до юридического и партнёрского гейта.

## 8. Дизайн, Figma и анимация

### Утверждено

- Figma account: `y.a.a.c.a.b@gmail.com`.
- Figma file: `6QGCbvU9NIW9Ba27LpDWLn`, page `6:2`.
- Общее направление motion: **«Рамка слота»**.
- Идея: спокойная глубина на главной, мягкий подъём редакционных фрагментов, короткое движение выбора даты и карточки площадки; действия доступны сразу, без автопрокрутки.
- Источники вдохновения, указанные владельцем: `motionsites.ai` и `omma.build`.
- Премиальная анимация обязательна в будущем motion-релизе, но её конкретный артефакт сначала согласуется отдельно.

### Не утверждено и не интегрировать

- `/home/art67/booker/outputs/design/booker-slot-frame-higgsfield.mp4`
- `/home/art67/booker/outputs/design/booker-slot-frame-higgsfield.png`

Связанные Higgsfield данные для поиска истории:

- workspace `2c402942-6ffb-4efc-bbdc-276f75d1c65f`
- project `d6166aaa-93ee-4e05-9ff5-c744ef454163`
- job `4985d4ab-9c5d-44df-8f95-817ada7d139d`

Не использовать эти файлы в web до явного «утверждаю». Следующая визуальная работа сначала возвращается владельцу как preview/макет. Motion должен поддерживать `prefers-reduced-motion`, быстрый первый кадр, доступный CTA и мобильную производительность.

Новый review-ready preview от 01.10.2026: `outputs/design/booker-slot-frame-v2-UNAPPROVED.html` и кадры desktop/mobile/reduced motion; спецификация `docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md`. Отдельный Higgsfield ambient study завершён, но содержит псевдотекст и не является готовым UI. **Все эти артефакты UNAPPROVED**. `apps/web` не изменён этим motion-срезом. Владелец должен посмотреть и утвердить конкретную композицию до интеграции.

## 9. Последние проверки web

До reconciliation-среза, который менял только API, были зелёными:

- 11 web unit tests;
- TypeScript (`npm run lint`);
- production build (`npm run build`);
- Deal Room E2E: 3 passed;
- Event Day Playwright helper: 6 passed;
- support browser E2E.

Эти результаты сохранены как историческое доказательство и не означают production/live E2E. При следующем изменении web запускать соответствующий unit/TypeScript/build и узкий Playwright сценарий заново.

## 10. Команды проверки

API:

```bash
cd /home/art67/booker/apps/api
.venv/bin/python -m ruff check booker_api tests alembic/versions
.venv/bin/python -m pytest tests/test_reconciliation.py -q
.venv/bin/python -m pytest tests/test_alembic.py -q
.venv/bin/python -m pytest tests/test_payments.py -q
.venv/bin/python -m pytest -q
# При установленном TEST_POSTGRES_DSN локальной тестовой БД:
.venv/bin/python -m pytest -q -m postgres_integration
```

Web:

```bash
cd /home/art67/booker/apps/web
npm run test:unit
npm run lint
npm run build
```

Playwright запускать узко по затронутому сценарию; полный E2E требует учитывать локальные server/port настройки в `playwright.config.ts` и helpers.

## 11. Известные ограничения и недоказанное

- Production не развёртывался в этой серии; нет production SHA и rollback package.
- Не проверены реальный Telegram/WebView сценарий, live payment, новый charge, payout, partner registry, банковский webhook и мобильный платёжный E2E.
- PostgreSQL reconciliation migration пока не прогнана на живом staging.
- Юридические тексты — draft; реквизиты оператора и схема денег не утверждены.
- Большой dirty diff содержит несколько вертикалей. Перед релизом его нужно разбить на обозримые commits/PRs, не теряя зависимости миграций.
- Существующие документационные статусы могут отставать от кода; этот файл фиксирует наиболее свежую проверенную точку, но фактический diff всегда важнее.
- Анимация «Рамка слота» утверждена как направление, конкретный Higgsfield preview не утверждён.

## 12. Точный следующий порядок действий

1. Admin reconciliation API, payout eligibility guard, локальный PostgreSQL harness и backup/restore исправления добавлены в dirty working tree. Последний полный API прогон: **330 passed, 4 skipped**; четыре skip — PostgreSQL integration без `TEST_POSTGRES_DSN`. Профильный backup/restore набор **11 passed**; локальный синтетический drill PASS. PostgreSQL runtime proof не получен. Ruff, Bash `-n` и `git diff --check` PASS; ShellCheck недоступен. Ветка `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 188 изменённых/неотслеживаемых путей при последней сверке; commit/push/deploy не было.
2. Следующий конкретный backend шаг: предоставить выделенную локальную PostgreSQL БД с именем, содержащим `test`, и ограниченной учётной записью, установить `TEST_POSTGRES_DSN`, затем из `apps/api` запустить `.venv/bin/python -m pytest -q -m postgres_integration`. Сохранить вывод и отдельно проверить, что временная schema удалена. Без этого PostgreSQL concurrent import и migration proof — **открытый внешний gate**. После него нужна миграция на копии фактической непустой БД, включая DDL lock time; production не использовать.
3. Следующий ops шаг: спроектировать шифрование/off-site хранение с ключами и согласованный DB+uploads snapshot, задать лимиты безопасного восстановления и полноценный read-only dry-run, затем выполнить staging restore с API smoke и замером RTO. Локальный синтетический drill в `docs/ops/RESTORE_DRILL_LOG.md` не заменяет это подтверждение.
4. Review-ready motion preview «Рамка слота» подготовлен и передаётся владельцу на решение; reduced-motion и мобильные параметры описаны в `docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md`. До явного «утверждаю» не переносить артефакт в web.
5. После решения владельца продолжать только разрешённый дизайн или независимый backend-срез; перед релизом повторить проверки затронутого сценария и разбить большой diff на обозримые commits/PRs только по отдельной команде.

## 13. Автоматизация прогресса

В Codex активна hourly heartbeat automation **«Прогресс Букера каждый час»**. Её файл на машине: `/home/art67/.codex/automations/automation/automation.toml`. Она относится к текущему чату; новый чат должен проверить, нужно ли перенести или пересоздать уведомление, а не создавать дубликат автоматически.

## 14. Готовый первый prompt для нового чата

> Продолжай разработку «Букера» из `/home/art67/booker`. Сначала прочитай `AGENTS.md`, `docs/product/CONTRACT.md` и `docs/PROJECT_STATE.md`. Проверь фактические `git status --short --branch`, `git rev-parse HEAD` и `git diff --check`. Рабочее дерево намеренно грязное: ничего не reset/clean/force-checkout, не удаляй `:memory:.ses`. Ветка `feat/sitewide-lime-design`, последний проверенный HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`; после backup/restore-среза было 188 изменённых/неотслеживаемых путей. Admin reconciliation API, payout guard и локальный backup/restore drill выполнены; последний полный API suite 330 PASS, 4 SKIP. Четыре opt-in PostgreSQL сценария пропущены без `TEST_POSTGRES_DSN`; следующий backend шаг — запустить их на выделенной локальной тестовой БД и проверить очистку временной schema. Ops гейты: шифрование/off-site хранение, согласованный DB+uploads snapshot и staging restore с API smoke/RTO; локальный drill их не закрывает. Motion preview «Рамка слота» требует отдельного утверждения до интеграции в web. Не подключай live acquiring; законченные проверенные части коммить самостоятельно, при необходимости отправляй в текущую рабочую ветку для GitHub CI и продолжай независимую работу до результата проверок. Не включай соседний dirty diff, секреты и временные файлы. Деплой согласовывай отдельно.

## 15. Последний security/SLA-срез 01.10.2026

Два read-only агента проверили object authorization и вложения. Добавлена матрица `docs/ops/OBJECT_AUTHZ_MATRIX_2026-10-01.md` на 163 операции; она показывает реальные зависимости FastAPI и прямые ACL-вызовы, но не доказывает полное покрытие отрицательными тестами. Исправлены три мутации из роли viewer (stub payment, hold, dispute), утечка статуса закрытого спора через evidence endpoint, отдача вложения по клиентскому MIME и admin upload/download без 2FA. Повтор `clean` проверяет целостность, чтение файла ограничено лимитом. График поддержки, утверждённый владельцем, задан для двух срочных интентов: ежедневно 10:00–22:00 МСК; срок рассчитывается API в рабочем окне. Профильный набор 42 PASS, полный API suite **338 PASS, 4 SKIP** (PostgreSQL без DSN), Ruff/compileall/diff-check PASS. Web в этом срезе не менялся.

Открытые риски: ручное `clean` не равно AV-сканированию; multipart body может буферизоваться до endpoint guard при прямом доступе к API; правила хранения файлов после отмены/истечения hold не утверждены; публичность закрытых briefs требует решения. Не доказаны PostgreSQL runtime, production и адресные отрицательные сценарии всех 163 операций. Внутренний срок теперь вычисляется, но адресный канал просрочки не настроен. Старый prompt в разделе 14 содержит состояние до этого среза; при продолжении приоритет у этого раздела и свежего `git status`/тестов.

## 16. Продолжение object auth 01.10.2026

Состояние при проверке: `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 190 изменённых/неотслеживаемых путей всего дерева; `git diff --check` PASS. Два read-only агента проверили support/messages и attachments/disputes/private resources. Исправлены создание договора ролью viewer или platform admin без членства заказчика, чувствительные admin-операции без настроенного TOTP при выключенном глобальном флаге, принятие изменённого clean-файла как доказательства спора. Каждый дефект сначала воспроизведён красным HTTP-тестом. Добавлены отрицательные проверки по чужому обращению внутри той же организации, support admin step-up на отдельных маршрутах, viewer в Deal Room, чужому event в брифе и assignment/resolve спора без TOTP. В матрице `docs/ops/OBJECT_AUTHZ_MATRIX_2026-10-01.md` теперь **32/163** операций с адресно сопоставленным отрицательным тестом; оставшиеся строки не помечены PASS.

После финальных правок полный API suite: **345 PASS, 4 SKIP** (без `TEST_POSTGRES_DSN`); Ruff, compileall, `git diff --check` PASS. Web, motion, production, commit/push/deploy не затронуты. Следующий безопасный шаг: продолжить приоритетные negative tests из матрицы, затем PostgreSQL integration на выделенной тестовой БД и операционное решение для AV, раннего multipart limit и step-up на остальных admin-мутациях. Не объявлять весь API проверенным по 32 адресным маршрутам.

## 17. Money/private-read authz: второй транш 01.10.2026

Свежий Git срез: `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 191 изменённый/неотслеживаемый путь; `git diff --check` PASS. Два read-only агента проверили money/admin и private-read области, затем итоговые дельты. Красными тестами подтверждены и узко исправлены ложный idempotent replay изменённого внешнего отчёта, утечка исторических заявок/броней через mutable org-поля, захват создания оффера новым org и admin-отмена без TOTP. Совместимость проверена отдельно: заявки без `Conversation` остаются в списке, но создание оффера по ним по-прежнему получает 409 до восстановления достоверных сторон; dual member с ролью manager у исполнителя может отменить бронь при viewer роли у заказчика. Дополнительные negative tests покрывают привязку внешнего report к payment и файла к booking, TOTP/reconciliation/reminder, приватные event views. Матрица `docs/ops/OBJECT_AUTHZ_MATRIX_2026-10-01.md`: **43/163** операций с точными отрицательными тестами, остальные не объявлены PASS.

Финальный полный API pytest на последних изменениях: **355 PASS, 4 SKIP** (PostgreSQL integration без `TEST_POSTGRES_DSN`). Ruff, compileall и `git diff --check` PASS. Web/motion/production, commit/push/deploy не затронуты. Открытые гейты: legacy запросы без immutable snapshot требуют backfill/операционного решения; ранний body limit для multipart и reconciliation, AV, PostgreSQL runtime и production E2E отсутствуют. Продолжать с нового `git status` и проверять эти факты, не опираться на старые итоговые числа разделов 15–16.

## 18. Identity/supply authz: третий транш 01.10.2026

Свежий срез: `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 191 изменённый/неотслеживаемый путь всего дерева. Два независимых read-only агента проверили identity/invitations и supply/publication, затем итоговые изменения. Красными тестами воспроизведены старые сессии и другие действующие ссылки после сброса пароля, ошибка naive/aware даты в SQLite, публикация с единственной записью `busy` и повторная публикация площадки с новым залом без календаря. Исправления: атомарный расход reset-токена, отзыв остальных ссылок и всех сессий, сериализация login/reset по строке пользователя на PostgreSQL и ранняя write-блокировка SQLite, календарная запись `open|held|confirmed` у каждого зала. Тестовая фикстура импорта теперь заполняет оба зала.

Новые negative tests покрывают добавление участника и переключение организации outsider/viewer, права и replay приглашений, запрет manager/outsider менять publication evidence и публикацию, привязку iCal/отпуска к организации. Матрица `docs/ops/OBJECT_AUTHZ_MATRIX_2026-10-01.md`: **61/163** операций с точными тестами, 102 без адресного сопоставления. Финальный полный API pytest: **362 PASS, 4 SKIP** (PostgreSQL integration без `TEST_POSTGRES_DSN`); профильный набор 42 PASS, identity/invitations 11 PASS и файловый SQLite concurrency-тест PASS, Ruff/compileall/diff-check PASS. Web/motion/production, commit/push/deploy не затронуты.

Открытые гейты: гонка login/reset проверена на файловой SQLite; PostgreSQL-конкурентность и одновременный расход токена не подтверждены runtime; услуга не привязана к конкретному верифицированному профилю; публичная карточка остаётся видимой при полном перекрытии `open` отпуском/iCal — нужна продуктовая политика. SQLite `BEGIN IMMEDIATE` удерживает общую write-блокировку и может задерживать другие записи при высокой нагрузке; это нужно проверить при выборе production-БД. Ранний body limit, AV, legacy `Conversation` provenance и production E2E по-прежнему открыты. Продолжать с нового Git-среза и точных тестов, не принимать исторические числа выше за текущие.

## 19. Supply/public integrity: четвёртый транш 01.10.2026

Срез: `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 192 изменённых/неотслеживаемых пути всего дерева. Публичная услуга теперь связана с конкретным профилем той же организации, проходит текущий профильный publication gate и скрывается при снятии этого профиля с публикации. Автоматическая привязка, миграция `f5b0c1d2e3f4` и повторный runtime backfill работают только при единственном профиле той же категории; явная привязка и публичное чтение требуют такого же совпадения; неоднозначные услуги остаются скрытыми до ручной привязки writer через `PUT /services/{id}/profile`. Снятый с публикации профиль больше не раскрывает cached name/city в списке избранного. Viewer не может публиковать shortlist организации; личное избранное остаётся доступным. Адресные отрицательные тесты воспроизвели прежние утечки до правок, затем проверили чужой профиль, viewer, неоднозначность, повторное восстановление схемы и непригодность профиля. Матрица доступа: **68/164** операций с адресно сопоставленными negative tests.

Профильный набор: **44 PASS**. Полный API pytest: **370 PASS, 4 SKIP** (`TEST_POSTGRES_DSN` отсутствует). Ruff, compileall и `git diff --check` PASS. Продуктовый контракт не определяет, скрывать ли профиль целиком, если весь `open` горизонт ≥30 дней перекрыт отпуском/iCal/занятостью; логика видимости здесь не менялась. Требуется решение по этому вопросу и по публикационному значению `stale` freshness; объём legacy неоднозначных услуг в production не измерен. PostgreSQL runtime, web, motion, production E2E не проверялись. Commit/push/deploy не выполнялись. Следующий шаг: согласовать политику публичной видимости при полном перекрытии календаря, затем отдельно испытать миграцию и конкурентность на выделенной PostgreSQL базе.

## 20. Ранний предел загрузок: пятый security-транш 01.10.2026

Ветка `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, dirty tree 194 изменённых/неотслеживаемых пути без reset/clean/force checkout; файл `:memory:.ses` сохранён. Большой запрос к `POST /bookings/{booking_id}/attachments` теперь получает 413 до multipart-парсера по объявленному размеру или фактически принятым байтам, включая поток без `Content-Length` и заниженный заголовок. Лимит тела = `BOOKER_MAX_UPLOAD_BYTES + 64 KiB` на multipart-обрамление; отдельный предел файла остаётся `BOOKER_MAX_UPLOAD_BYTES`. Временный буфер после 64 KiB переносится из памяти на диск, его I/O вынесен из event loop. Исправлен ложный 413 для допустимого файла ровно на файловом лимите. Красные тесты подтвердили оба прежних дефекта до правки. Независимый read-only обзор проверил итоговый путь и указал на остающуюся нагрузку временного диска до авторизации.

Адресные тесты вложений: **15 PASS**. Финальный полный API suite: **374 PASS, 4 SKIP** (PostgreSQL без `TEST_POSTGRES_DSN`); Ruff, compileall, `git diff --check` PASS. Матрица доступа остаётся **68/164** операций с адресно сопоставленными отрицательными тестами: для upload-операции добавлены случаи oversized body. `clean` остаётся ручным решением с SHA-256/размером, а не антивирусным заключением; реальный AV и production object storage не проверены. Время медленной загрузки, параллельные соединения и нагрузка на временный диск требуют runtime-проверки вместе с reverse proxy. Approved направление motion «Рамка слота» остаётся только UNAPPROVED preview, web/motion не менялись. Production, commit/push/deploy не выполнялись.

Текущая оценка общей подтверждённой готовности: **73%** (после предыдущих 72%; прибавка относится к локально проверенному upload-срезу, не к production readiness).

## 21. Support secrets / high-risk authz: шестой транш 01.10.2026

Свежий срез: ветка `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, 194 изменённых/неотслеживаемых пути всего дерева; `git diff --check` PASS. Независимый read-only аудит нашёл два подтверждённых дефекта поддержки: самостоятельный `sk_live_…` сохранялся и попадал в handoff, а fingerprint сообщения вычислялся по исходному секрету. Первый дефект воспроизведён красным HTTP-тестом. Маскирование расширено на распространённые самостоятельные API/GitHub/Slack token-префиксы; fingerprint теперь считается по очищенному тексту. Профильные тесты проверяют БД, handoff-тикет, первое сообщение оператора, ручное обращение и совпадающие отпечатки для разных скрытых ключей. Replay ранее записанного fingerprint того же исходного сообщения сохраняется и лениво переводит его в безопасное значение. Исторические строки и отпечатки без replay не очищены автоматически; перед выпуском с данными нужен аудит и отдельный backfill/retention plan.

Красным тестом выявлено, что `/admin/verifications` принимал произвольный `target_type` и трактовал его как площадку. Теперь схема ограничена `artist|venue`. Новые отрицательные тесты покрывают outsider и участника той же организации для сессии помощника, сообщений, handoff и feedback; чужую организацию при создании сессии; не-администратора на verification/dispute/outbox/audit и статусе/модерации/freshness площадки без побочных изменений. Матрица доступа: **86/164** операций с адресными negative tests (рост с 68/164, включая найденные ранее написанные тесты conversation и Event Day). Профильный support/admin/messages/Event Day набор **62 PASS**. Финальный полный API suite **380 PASS, 4 SKIP** (нет `TEST_POSTGRES_DSN`); Ruff, compileall, `git diff --check` PASS.

Календарь SLA для срочных случаев подтверждён в конфигурации и тестах: ежедневно 10:00–22:00 `Europe/Moscow`, срок переносится через конец окна и выходные без паузы. Tenant isolation, handoff state machine и close/reopen CAS подтверждены кодом и локальными отрицательными тестами; настоящая параллельная гонка на PostgreSQL не проверена. Для admin verification/venue moderation/outbox принудительный TOTP step-up не добавлялся: это отдельное решение операционной политики. Итоговый независимый read-only обзор снял прежние замечания и не выявил нового подтверждённого обхода P0/P1/P2; его собственный API-прогон не завершился, поэтому тестовым доказательством служит локальный полный suite выше. Motion preview «Рамка слота» остаётся UNAPPROVED; web/motion/production не менялись. Commit/push/deploy не выполнялись. Общая подтверждённая готовность оценена в **74%** против предыдущих 73%; это локальная проверка, а не production readiness.

## 22. Исторические секреты поддержки: седьмой security-транш 01.10.2026

Добавлен scoped maintenance `apps/api/booker_api/support_secret_backfill.py` и инструкция `docs/ops/SUPPORT_SECRET_BACKFILL.md`. Один запуск охватывает одну организацию либо личные записи одного пользователя без организации. Dry-run возвращает только счётчики и непрозрачный HMAC-токен точного плана. Apply требует свежую сессию, совпадение числа изменений и токена, отсутствие расхождения очищенных копий тикета/первого сообщения и связей между tenant; запись проходит одной транзакцией. Из allowlist очищаются текст тикетов, сообщений, заметок, обменов и feedback, соответствующие fingerprint пересчитываются либо обнуляются там, где исходный payload нельзя восстановить. Идентификаторы, ключи идемпотентности, статусы и аудит сохраняются. Универсальный outbox и внешние копии не затронуты.

Пять адресных тестов backfill проверили dry-run, применение, повторный запуск, изоляцию двух организаций, личный scope, расхождение копий, связь через чужой tenant, отказ при устаревшем плане и незавершённой сессии, отсутствие секрета в отчёте/ошибке CLI и replay старого сообщения. Два дополнительных negative HTTP-теста проверили запрет atomic hold для viewer/outsider без частичного захвата и запрет списка споров постороннему. Матрица доступа: **91/164** маршрута с адресно сопоставленными отрицательными тестами. Профильный набор **13 PASS**; полный API suite **387 PASS, 4 SKIP** (`TEST_POSTGRES_DSN` отсутствует). Ruff, compileall и `git diff --check` PASS. Независимый read-only reviewer не нашёл оставшихся конкретных P1/P2 после исправлений; он тесты не запускал.

Это доказательство только на локальной синтетической SQLite. Скрипт **не запускался на действующей или staging БД**; фактические исторические секреты, объём и внешние копии неизвестны. Перед применением нужны защищённая резервная копия, остановка support-записи, dry-run того же scope и PostgreSQL/нагрузочная проверка на копии данных. Платёжный production, web/motion, commit/push/deploy не менялись. Ветка `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`, dirty tree 197 путей; ничего не reset/clean. Общая подтверждённая готовность: **75%** (ранее 74%); production readiness этим не подтверждена.

## 23. Риск-маршруты и полнота помощника: восьмой локальный транш 01.10.2026

Оставшиеся без сопоставления маршруты ранжированы в `docs/ops/OBJECT_AUTHZ_MATRIX_2026-10-01.md`. Добавлены адресные отрицательные сценарии для webhook с поддельной подписью (без изменения платежа, брони, webhook event и money movement), admin очередей/истории/TOTP, закрытия чужого брифа viewer/другим tenant, отметки прочтения чужого диалога, списка обращений поддержки для соучастника организации, и переиспользованы подтверждённые тесты SSE, expire holds, shortlist/revoked link и consent. В `/messages/inbox` устранён порядок проверки `X-Booker-Org`: пользователь без организаций теперь получает 403 на чужой заголовок, а не пустой 200. Счётчик матрицы: **112/164** операций с сопоставленным отрицательным сценарием, включая проверки ACL, подписи и состояния; это не полное authz-покрытие.

Помощник поддержки локально проверен по аккаунту/входу, бронированию, оплате и возврату, документам, профилю площадки/исполнителя и передаче оператору. Добавлены ограниченные ответы по документам и профилям без утверждения наличия/подписания документа, юридической силы, статуса карточки, денег или брони. Оплата/возврат остаются передачей человеку; срочные случаи сохраняют приоритет. Профильный ACL/support набор **69 PASS**; отдельные адресные webhook и TOTP тесты **2 PASS**. Полный API suite после всех правок **408 PASS, 4 SKIP** (PostgreSQL без `TEST_POSTGRES_DSN`). Ruff, compileall, `git diff --check` PASS. Независимый read-only reviewer не нашёл конкретного P1/обхода прав или ложных обещаний.

Открытый P2 ревью: список inbox сортирует ветки по времени последнего по sequence сообщения; если историческая метка времени этого сообщения неверна/сдвинута назад, порядок веток может быть неверным. Межветочного серверного номера доставки в схеме нет; исправление потребует отдельного решения по данным и миграции. Остальные **52/164** маршрута не имеют адресного сопоставления в матрице. Подпись webhook проверена только для локального stub, live acquiring закрыт. PostgreSQL/staging/production, web/motion и live E2E не проверялись; commit/push/deploy не выполнялись. Ветка и HEAD не менялись, dirty tree 197 путей. Подтверждённая общая готовность: **76%** (ранее 75%); это локальная оценка, не релизный допуск.

## 24. Порядок инбокса и ACL событий: девятый локальный транш 01.10.2026

Красный тест воспроизвёл неверный порядок веток, когда `created_at` последнего по `sequence` сообщения сдвинут назад. Добавлено отдельное серверное `messages.received_at`, по которому сортируется активность веток; одинаковые метки разрешаются детерминированно по ID диалога, пустые ветки идут после активных. `created_at` остаётся отображаемой датой, а непрочитанность по-прежнему считается из `sequence`. Новая Alembic-ревизия `f8b4c5d6e7f8` и SQLite runtime-adoption заполняют legacy `received_at` из доступного `created_at`, ограничивая будущие даты временем backfill. Миграция умеет принять уже добавленный runtime-столбец; на непустой таблице downgrade отказывается терять значения. Отдельный красный тест показал, что повторная инициализация SQLite сбрасывала `last_read_sequence` по сдвинутому `created_at`; теперь backfill read marker выполняется только при первом добавлении legacy-столбца.

Шесть новых отрицательных HTTP-тестов событий проверяют чужую организацию и viewer для списков/деталей, `check-out`, требований, requests и quick request с event ID; отказ не создаёт записей и не меняет состояние. Подтверждённого дефекта в этих маршрутах не найдено. Матрица теперь содержит **118/164** маршрутов с сопоставленным отрицательным сценарием (не 118 полных authz-проверок); осталось 46. Профильный inbox/event/Alembic набор **33 PASS**, полный API suite **417 PASS, 4 SKIP** (нет `TEST_POSTGRES_DSN`). Ruff, compileall и `git diff --check` PASS. Независимый read-only reviewer после исправлений не нашёл новых конкретных P1/P2.

Пределы: фактическую межветочную хронологию legacy-сообщений с датой, ошибочно сдвинутой назад **до** миграции, восстановить из текущих полей нельзя; backfill сохраняет доступную оценку, будущие даты зажимает. PostgreSQL rewrite `messages` одной операцией требует испытания на защищённой копии с замером DDL lock; реальная БД не открывалась. Ветка `feat/sitewide-lime-design`, HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`; concurrent юридическая задача работает только в `docs/legal/`, этот транш её файлы не менял. Web/motion, production, commit/push/deploy не выполнялись. Подтверждённая общая готовность: **77%** (ранее 76%); это локальная оценка, не production readiness.

## 25. Изменения supply, claims и отзывы: десятый локальный security-транш 01.10.2026

Приоритетная сверка оставшихся маршрутов показала, что money/refund/payout/reconciliation и вложения/скачивание уже имеют адресные отрицательные сценарии в матрице. Новый набор из 20 отрицательных HTTP-сценариев проверил viewer и владельца другой организации на изменениях доказательств публикации артиста/площадки, фотографий и залов площадки, тарифов, слотов артиста/зала и услуги из шаблона. Каждый отказ 403 сверяет неизменность затронутых таблиц и аудита; дефектов в этих обработчиках не воспроизведено.

Два красных теста выявили реальные ошибки ролей: viewer мог создать claim на владение площадкой от имени организации и опубликовать отзыв по завершённой сделке. Для claim теперь требуется owner/admin организации; для отзыва — owner/admin/manager стороны сделки. Отказы проверены без VenueOwnershipClaim/Review/AuditLog записей. Чужая организация при создании обращения поддержки и сохранённого поиска, а также чтении списка поисков, получила адресные тесты без побочных записей. Ещё один красный тест выявил, что публичные списки отзывов раскрывали `booking_id` и `author_user_id`; эти поля удалены из публичного представления, ответ автору при создании сохранён. Независимый read-only reviewer после исправлений не нашёл новых конкретных P1/P2.

Матрица содержит **134/164** маршрута с сопоставленным отрицательным сценарием; 2 новых публичных GET-списка отзывов отмечены как privacy, а не authz. Остаётся 30 маршрутов. Профильный набор **37 PASS**; финальный полный API suite **441 PASS, 4 SKIP** (`TEST_POSTGRES_DSN` отсутствует). Ruff, compileall и `git diff --check` PASS. PostgreSQL/staging/production и web/motion не проверялись; `docs/legal/` принадлежит параллельной задаче и не менялся этим траншем. Commit/push/deploy не выполнялись. Ветка/HEAD без изменений: `feat/sitewide-lime-design`, `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`. Общая подтверждённая готовность: **78%** (ранее 77%); релизные гейты открыты.

## 26. Остальные маршруты и fallback поддержки: одиннадцатый локальный транш 01.10.2026

Из 30 строк без адресного отрицательного сценария проверены 27. Создание артиста, площадки и события отклоняет viewer и владельца другой организации без новых записей/аудита. Изменение избранного не позволяет воздействовать на чужую организацию; удаление чужого ID сохраняет строку. Приватность уведомлений, supply-completeness и `/me`, одинаковый ответ восстановления на существующий и неизвестный email, отсутствие побочных записей при регистрации без принятия условий и анонимном создании организации, а также сохранение чужой сессии после анонимного logout подтверждены тестами. Публичные черновики и непроверенный research import скрыты в деталях, поиске, индексе, demo и compare; публичные briefs не выдают поля связанного частного события. Для `POST /promo/events` проверено только игнорирование неизвестного имени без записи в аудит (state, не authz).

Матрица теперь содержит **161/164** маршрута с адресным отрицательным сценарием разных типов: authz, privacy, signature, consent, state. Оставшиеся три — публичные `GET /health`, `GET /categories`, `GET /service-templates`; их обычная доступность проверена, но подходящего отрицательного сценария нет. Счётчик не означает полного authz-покрытия. Ответ помощника на неизвестную или неподдерживаемую тему теперь явно сообщает предел видимости данных и предлагает «Передать человеку», не повторяя присланные ID/секреты. Старую тестовую фикстуру promo, повторно монтировавшую уже подключённый роутер, удалили по замечанию независимого read-only ревьюера; новых подтверждённых P1/P2 тот не нашёл.

Полный API suite, начатый до последних двух добавленных сценариев и удаления фикстуры promo: **473 PASS, 4 SKIP**. Последующий профильный прогон финального состояния: **24 PASS**; Ruff, compileall и `git diff --check` PASS. `TEST_POSTGRES_DSN` отсутствует; PostgreSQL, staging, production и live E2E не проверялись. `docs/legal/`, web/motion, commit/push/deploy этим траншем не затрагивались. Ветка/HEAD прежние: `feat/sitewide-lime-design`, `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`; рабочее дерево намеренно грязное. Подтверждённая общая готовность: **79%** (ранее 78%), без релизного допуска.

## 27. Публичные инварианты и локальный операторский путь: двенадцатый транш 01.10.2026

Для трёх публичных строк матрицы добавлены адресные инварианты без искусственного ACL-запрета: `/health` не возвращает подставленные email API key и merchant ID, `/categories` не публикует скрытую категорию и повторное чтение не создаёт новых строк, `/service-templates` отдаёт только справочные поля и стабильный ответ. Целевые API-тесты **3 PASS**. Матрица теперь **164/164** по адресным отрицательным инвариантам разных типов, **не** по полноте авторизации.

Существующий браузерный сценарий поддержки дополнен настоящим ответом оператора через локальный API: после handoff обычный пользователь получает 403 на admin queue, администратор с TOTP видит очередь и тикет по ID, отправляет ответ, а заказчик видит его после reload. На отдельной временной SQLite support Playwright **1 PASS** после итоговой правки. Независимый read-only reviewer указал, что первые 100 строк очереди не обязаны включать новый тикет на накопленной БД; тест поэтому проверяет доступ к очереди и конкретный тикет по ID, не заявляя полноту списка. Ещё одно замечание уточнило формулировку матрицы по двум проверенным secret-полям `/health`.

Повторный полный API suite на текущем коде: **477 PASS, 4 SKIP** (`TEST_POSTGRES_DSN` отсутствует). Web TypeScript PASS, unit **11 PASS**, Next.js production build PASS. Подробный requirement-by-requirement аудит: `docs/ops/COMPLETION_AUDIT_2026-10-01.md`. Нерешённые гейты: утверждение детальных Figma-экранов и motion, юридический/партнёрский live-payment допуск, PostgreSQL и staging/production E2E, реальный операторский UI и пилотные метрики. `docs/legal/` и UNAPPROVED motion не трогали; commit/push/deploy не выполняли. Подтверждённая общая готовность: **80%** (ранее 79%); это локальная оценка без релизного допуска.

## 28. AV-вердикт и fail-closed карантин: тринадцатый локальный транш 01.10.2026

Добавлен опциональный `BOOKER_AV_PROVIDER=clamd` с локальным Unix-сокетом и ограниченным по общему времени `INSTREAM` клиентом. Загрузка по-прежнему создаёт `quarantined`; отдельный TOTP-защищённый admin `POST /admin/attachments/{id}/scan` читает файл только после проверки размера/SHA-256. `OK` сохраняет `clean`, `FOUND` — `blocked`; таймаут, отсутствие сокета и неизвестный ответ оставляют карантин. При включённом `clamd` ручное `clean` запрещено, старые ручные `clean` перестают быть скачиваемыми до повторного сканирования. Общий предикат допуска использует записанные `av_verdict_provider` и `av_verdict_sha256` в download, Deal Room и evidence. Новая Alembic-ревизия `f9c5d6e7f8a9` и SQLite runtime adoption добавляют происхождение вердикта и токен попытки.

По замечанию независимого read-only reviewer устранены две гонки: старт и завершение проверки условно обновляют строку с идентификатором попытки; ручное `blocked` не перезаписывается поздним `clean`, параллельное сканирование получает 409. Зависшая после сбоя попытка повторяется только после защитного интервала. Второе read-only ревью не выявило оставшихся конкретных P1/P2. Подробности и условия включения: `docs/ops/AV_SCAN.md`.

Локальная проверка: профильный AV/attachments/Alembic набор **45 PASS**, полный API suite **488 PASS, 4 SKIP** (нет `TEST_POSTGRES_DSN`), Ruff/compileall/`git diff --check` PASS. Отдельный Alembic `upgrade head` на временной SQLite и проверка четырёх AV-столбцов PASS. Детерминированный fake-scanner через Unix-сокет проверил clean/FOUND/error, пропавший сервис, старое ручное решение и пересечение попыток. Настоящий `clamd`, свежесть сигнатур, работа на PostgreSQL/staging/production и нагрузка не проверены; режим `manual` по умолчанию не является AV-сканированием. Матрица: **165/165** маршрутов с адресными отрицательными инвариантами разных типов, не полное authz-покрытие. `docs/legal/`, web/motion, commit/push/deploy не затрагивались. Подтверждённая общая готовность: **81%** (ранее 80%), без релизного допуска.

## 29. Запечатанный backup и единый P0-план: четырнадцатый локальный транш 02.10.2026

В `infra/backup_crypto.py` добавлен opt-in `BOOKER_BACKUP_FORMAT=sealed`: потоковое AES-256-GCM шифрование `.bke`, аутентификация заголовка и tag до чтения tar для восстановления. Ключ — 32 бинарных байта, проверяется владелец и режим `0600` через дескриптор без следования symlink; ключ не размещается в backup/upload-каталогах. `backup-booker.sh` публикует архив только после проверки, `restore-drill.sh` определяет формат по содержимому и поддерживает строгий отказ от legacy. Ограничены размеры архива/содержимого и число tar-записей; retention обрабатывает `.bke`. Старый tar.gz по умолчанию остаётся совместимым. Инструкция и риски — `docs/ops/BACKUP_SEALED.md`, запись — `docs/ops/RESTORE_DRILL_LOG.md`.

Синтетический SQLite+uploads round-trip, неверный/сменённый ключ, tamper/truncate/append, права, preflight, legacy policy и retention: профильный набор **16 PASS** после последних защитных правок. Полный API suite был выполнен до последних защитных правок и дал **493 PASS, 4 SKIP**; 4 skip — opt-in PostgreSQL без `TEST_POSTGRES_DSN`. Независимый reviewer указал на риск копирования открытого staging при off-site синхронизации: для sealed снимок перенесён вне backup-каталога, вложенный staging запрещён, отдельные старые временные каталоги очищаются при следующем запуске. После аварии оператор всё ещё должен проверить временный plaintext в `/tmp`. Ревью также уточнило, что компенсирующее исправление external payment отсутствует; план не считает его локально проверенным. Это локальный результат, не staging/prod. Двухстековый план P0 A–F, ops/security и Booker acceptance актуализирован в существующем `docs/product/FINAL_IMPLEMENTATION_PLAN.md` с отдельными внешними gates; `docs/legal/` не редактировался. Остались KMS/off-site, согласованный DB+uploads snapshot, PostgreSQL/staging restore, реальный AV, юридический/партнёрский live-payment GO, утверждение статичного Figma и пилотные метрики. Общая локальная оценка **82%** (ранее 81%), без релизного допуска; commit/push/deploy не выполнялись.

## 30. Fail-closed production config: пятнадцатый локальный транш 02.10.2026

Добавлен явный `BOOKER_RUNTIME_ENV=production`: FastAPI проверяет payment mode (`external`/`disabled`), webhook secret, обязательную admin 2FA, канонический HTTPS URL, закрытый CORS и допустимые notification transports **до** `init_schema`. Прямой demo seed отказывает в production. Сессии остаются случайными непрозрачными токенами в БД; неподдерживаемый `BOOKER_SESSION_SECRET` теперь отвергается в production, а `BOOKER_ALLOW_DEMO_SEED=1` не проходит startup gate. `audit` in-app transport сохраняет прежнюю запись событий без отправки и не может обслуживать email/SMS/push. Local/test/staging defaults не менялись; live acquiring не включался.

В `infra/systemd/booker-api.service` production-режим закреплён в `ExecStart`, а `infra/preflight_booker_api.py` проверяет итоговый unit+защищённый env-файл до остановки сервисов в deploy script. Preflight требует `BOOKER_DATABASE_URL` и уникальный `BOOKER_WEBHOOK_SECRET` из env-файла; дефолтный файл только с адресом БД теперь приведёт к отказу deploy **до** остановки работающих сервисов. Runbook: `docs/ops/PRODUCTION_CONFIG_GATE.md`. Независимый read-only reviewer обнаружил и помог закрыть риск остановки API при deploy, обход через EnvironmentFile и demo seed, слабый повторяющийся секрет, отсутствие DB URL в preflight и audit transport на внешних каналах.

Локальные доказательства: production config + notifications **30 PASS** после итогового запрета `export` и относительной SQLite в preflight; полный API suite **515 PASS, 4 SKIP** (без `TEST_POSTGRES_DSN`) был запущен до этих двух последних изменений только в preflight и его тесте. Ruff/Bash syntax/`git diff --check` PASS. Установленный production unit и содержимое защищённого env-файла не инспектировались; staging/production boot, реальный admin TOTP путь и deploy не выполнялись. Gate защищает следующий выпуск, но не подтверждает его. Общая локальная оценка **83%** (ранее 82%); `docs/legal/`, UNAPPROVED motion, commit/push/deploy не затрагивались.

## 31. Secret exposure gate: шестнадцатый локальный транш 02.10.2026

Добавлен `scripts/check_secret_exposure.py`: source inventory берёт tracked/untracked проектные файлы, не читая `.git`, вложенные `outputs` worktree, venv/node_modules, build/cache и пользовательские uploads. Отдельный `--deploy-payload` получает точный список rsync dry-run по общему `infra/rsync-booker-excludes.txt`, блокирует чувствительные имена, symlink, неизвестный бинарный файл и найденный секрет **до** передачи файлов. `infra/deploy-vps.sh` использует тот же exclude-файл и запускает gate до rsync; после своей web-сборки проверяет новую `.next` с защищённым env-файлом до переключения сервиса и возвращает предыдущую сборку при FAIL. Секреты и даже имена файлов не выводятся: только hash ID пути, строка и правило. Исключения — точные path+SHA-256 только для синтетических fixture и локальных dev DB-примеров.

CI jobs получили source/payload gate и зависимость API/web/E2E от него; каждый web build в основном и плановом E2E workflow сканируется после сборки. Сканер ловит типовые токены/private key, literal secret assignments, `NEXT_PUBLIC` secret names, URL БД с паролем, заданные env-canary; бинарные публичные медиа проверяются на точные сигнатуры/canary. Проверка публичного API и тестовых логов использует детерминированные canary для `/health`, `/readiness`, `/categories`, `/service-templates`, unauthenticated admin и неверного webhook. Подробности/ограничения — `docs/ops/SECRET_EXPOSURE_GATE.md`.

Локальная проверка: synthetic canary suite **8 PASS** на итоговом scanner/test, полный API suite **521 PASS, 4 SKIP** был запущен до последних двух scanner-only уточнений и дополнительного canary-теста; свежий `npm run build` PASS, source+deploy payload+build scan PASS, Ruff/Bash syntax/`git diff --check` PASS. Независимый read-only reviewer проверил правила и помог закрыть расхождение scanner/rsync, вывод секретного имени файла, VPS build gap, CI порядок, URL БД и бинарные canary. CI job, фактический VPS payload/env, staging/production ответы и реальные runtime-логи не проверены; высокоточный scanner не доказывает отсутствие неизвестных форматов секретов. `docs/legal/` и UNAPPROVED motion не редактировались, commit/push/deploy не выполнялись. Локальная общая оценка **84%** (ранее 83%), без релизного допуска.

## Срез 02.10: аудит зависимостей

Из начальных npm findings (1 critical, 4 high) обновлены Next до 15.5.27, sharp до 0.35.5, js-yaml и brace-expansion; PostCSS 8.5.23 закреплён override из-за старой версии, жёстко указанной в Next 15.5.27. Повторный `npm audit` — 0; `npm ci`, web 11 unit, TypeScript и production build — PASS. Добавлены pinned Python runtime/dev графы: `pip-audit` и локальный `uv pip compile`/`cmp` обоих lock — PASS, известных находок нет. CI теперь сверяет lock с `pyproject.toml`, сканирует npm/Python до unit/build/E2E и устанавливает Python из lock; сами GitHub Actions ещё не запускались. См. [отчёт с reachability](ops/DEPENDENCY_AUDIT_2026-10-02.md).

Локальный Playwright `flow.spec.ts` после обновления: **3 PASS, 1 FAIL**; упавшая проверка ожидает фразу в юридическом черновике, отсутствующую в текущей странице. Это не связано с обновлёнными пакетами, но полный E2E нельзя считать зелёным. Отдельная чистая Python 3.11 venv установлена из lock: 39 пакетов, `uv pip check` PASS, `pip-audit` установленного графа без известных находок (локальный `booker-api` пропущен). Полный локальный API suite после этого среза: **523 PASS, 4 SKIP**. Production/VPS не проверены. Независимое ревью выявило P1: текущий deploy меняет действующую API venv и web `node_modules` до сборки, а откат не восстанавливает оба набора; изменение deploy в этом срезе отложено, выпуск заблокирован до безопасного переключения обоих артефактов и проверки установленного графа. Никаких commit/push/deploy или правок `docs/legal/` и `UNAPPROVED` motion не было.


## 33. Общий rate limit: локальный транш 02.10.2026

Staging/production `RateLimiter` теперь использует атомарные DB-счётчики; для production SQLite это соседний постоянный файл, для PostgreSQL — таблица миграции `fa6d7e8f901b`. HMAC скрывает сырые ключи; backend failure закрывает auth/admin/OTP/upload/messages/requests/claim/webhook, analytics/promo явно fail open. Лимиты заявок/брифов/claim привязаны к user/org без IP, поэтому смена сети не сбрасывает бюджет. `X-Real-IP` принимается только от доверенного прямого peer; production unit и preflight требуют `--no-proxy-headers`. Отчёт с coverage/gaps: `docs/ops/RATE_LIMIT_DISTRIBUTED_2026-10-02.md`.

Локально: финальный полный API **537 PASS, 5 SKIP**, включая opt-in PostgreSQL limiter без `TEST_POSTGRES_DSN`; профильный **37 PASS**. Два FastAPI instance и два процесса разделяют счётчик; конкурентный тест допускает ровно N; restart, Retry-After, expiry, cleanup и отказ без побочных действий проверены. Миграция и исправление передачи пароля PostgreSQL в Alembic проверены локально без настоящей PostgreSQL; Ruff/compileall/secret gate/web build PASS. Независимый reviewer после правок не нашёл P0/P1. Настоящий PostgreSQL, многоworker staging с proxy и VPS не проверены; production deploy rollback и остальные внешние gates остаются открытыми. Commit/push/deploy не выполнялись, `docs/legal/` и motion не менялись. Общая оценка остаётся **84%**.

## 34. Утверждённое окно support SLA, локальный срез 02.10.2026

Решение владельца 01.10: ежедневно 10:00–22:00 МСК для двух срочных кодов, 30 рабочих минут для неявки в день события и 120 рабочих минут для оплаченной, но не подтверждённой брони. Действующая конфигурация `config.py` уже содержала `Europe/Moscow`, все семь дней и `closed_dates=[]`; unit/systemd и защищённый env не задают пустой override. Добавлены проверки границ окна, выходного и праздника, явного пустого env, queue/reopen, агрегированного ops monitor без PII. Web теперь называет окно и форматирует расчётную цель ответа именно в МСК без гарантии фактической смены. Сроки остальных категорий API не выдаёт.

После независимого read-only review закрыты краевые P2: production preflight сверяет календарь с утверждённым публичным окном и отклоняет даже JSON `true` вместо дня недели; web помечает цель после ответа, закрытия или reopen как историческую. Финальный адресный API-прогон **63 PASS**, web unit **12 PASS**, TypeScript, Next build, Ruff и diff-check PASS; source/deploy/build secret gate повторён после итоговой сборки. Маршрут дежурного, исключения праздников и реальный внешний transport не настроены; staging/production не проверены. Общая оценка остаётся **84%**. Эти результаты дополняют, а не заменяют исторические срезы выше.

## 35. Очередь оператора поддержки, локальный срез 02.10.2026

[Контракт и ограничения](ops/SUPPORT_OPERATOR_QUEUE_2026-10-02.md): отдельный интерфейс в `/admin`, фильтры/счётчики/ограниченные страницы, TOTP-сессия, назначение через CAS, история пользователя/оператора/системы и приватные заметки. Локальный браузерный сценарий на временной SQLite **1 PASS**: handoff, ACL, назначение, заметка, ответ без дубля, 409, close/reopen, 390 px. Web TypeScript, 13 unit-файлов и Next build PASS. Независимое статическое review не нашло P0/P1; открыто P2 по offset-пагинации при изменяющейся очереди. PostgreSQL, staging, production и дежурный маршрут не проверены; общая оценка **84%**. Commit/push/deploy не выполнялись.

## 36. Запросы субъекта данных и legal hold, локальный срез 02.10.2026

[Технический отчёт и карта данных](ops/DATA_SUBJECT_LIFECYCLE_2026-10-02.md): отдельные запросы `access|export|restrict|delete|correct`, приватные история/статусы, TOTP/CAS для оператора, append-only события, внутренний legal hold и только dry-run удаления. Полный экспорт и фактическое удаление выключены до policy. `restrict` локально снимает согласие на необязательные уведомления сохранённых поисков и запрещает повторное включение; transactional/audit записи не меняются. Миграция `fd9a012bc3d4` следует за fc, schema manifest остаётся draft/manual_block.

После независимого read-only review закрыты гонки hold/approval и restrict/opt-in общей блокировкой пользователя; новый hold атомарно возвращает ранее одобренное удаление на рассмотрение. Конкурентный тест двух SQLite соединений подтверждает сериализацию блокировки, но не полный PostgreSQL interleaving. Адресный API/schema/Alembic/saved-search suite **38 PASS, 2 SKIP** (нет `TEST_POSTGRES_DSN`); полный локальный API на финальном backend diff **604 PASS, 8 SKIP**. Playwright на временной SQLite **1 PASS**: пользовательский запрос, операторская очередь, hold, заблокированный план, снятие hold, мобильная ширина 390 px и задержанный ответ старой сессии после смены аккаунта. Web TypeScript, 14 unit-файлов и финальный Next build PASS; Ruff и diff-check PASS. Независимый reviewer после UI-исправлений не нашёл оставшихся конкретных P0/P1/P2. Общая оценка **84%**; PostgreSQL, staging и production не проверены, commit/push/deploy не выполнялись.

## 37. Версии юридических документов и согласия, локальный срез 02.10.2026

[Технический отчёт](ops/LEGAL_CONSENT_LEDGER_2026-10-02.md): семь черновых версий с SHA-256, неизменяемые события согласия, отдельные отметки оферты/политики/обработки/маркетинга и привязка регистрации к точному серверному пакету. Веб перед регистрацией сверяет хеши **всех семи отображаемых файлов** с API; при несовпадении блокирует форму. Черновая регистрация в local/test фиксирует только `test_acknowledgement`, а маркетинговая тестовая отметка не включает действующее согласие. Production без единой опубликованной редакции всех семи документов и отдельного publication flag закрывает регистрацию. Старый `2026-08-18-draft` в аудите не переписан; `legacy_unknown` обозначен явно. В профиле доступны история, отзыв и повторное принятие только новой опубликованной редакции.

Миграция `feab012bc3d5` следует за `fd9a012bc3d4`; единственная вершина, **39** ревизий. SQLite runtime и Alembic устанавливают DB guard для append-only истории и опубликованных редакций; schema manifest остаётся draft с `manual_block`, без допуска к production DB. Итоговый локальный API suite **615 PASS, 8 SKIP** (нет `TEST_POSTGRES_DSN`), адресный legal/identity/data-subject suite **22 PASS, 1 SKIP**. Web unit **68 PASS**, TypeScript и Next build PASS; Playwright на временной SQLite **7 PASS**, включая регистрацию, отзыв, блокировку при несовпадении только cookie-документа и задержанный ответ старой сессии. Ruff, `git diff --check`, source/deploy-payload/build secret gate PASS. Независимый финальный read-only review не нашёл конкретных оставшихся P0/P1/P2. Общая оценка **84%**; юридическое утверждение, PostgreSQL runtime, staging/production и live-публикация не проверены. `docs/legal/**` в этом срезе не редактировались, commit/push/deploy не выполнялись.

## 37. Реестр документов и журнал согласий, локальный срез 02.10.2026

[Технический отчёт](ops/LEGAL_CONSENT_LEDGER_2026-10-02.md): миграция `feab012bc3d5` после fd добавляет версии документов и append-only события согласий. Регистрация привязана к точным key/version/SHA-256, требует три отдельные обязательные отметки, оставляет маркетинг выключенным по умолчанию и в local/test явно называет действие подтверждением черновика. Production без полного опубликованного семидокументного пакета одной версии и отдельного publication gate закрыт. Исторические события не переписаны; отзыв и reaccept добавляют новые события. Runtime SQLite guard и миграционные SQLite/PostgreSQL triggers запрещают mutation истории и опубликованного содержания. Web закрывает регистрацию при расхождении отображаемого текста с API, защищает consent UI от задержанного ответа старого аккаунта и даёт отдельный путь reaccept.

Финальная локальная проверка: адресный API/schema suite **29 PASS, 1 SKIP**, полный API suite **615 PASS, 8 SKIP**, onboarding+consent Playwright на временной SQLite **7 PASS**. Web TypeScript, **16 unit-файлов**, Next production build, Ruff, `git diff --check` и source/deploy-payload/build secret gate PASS. Единственная Alembic-вершина `feab012bc3d5`, draft manifest содержит 39 ревизий и остаётся `manual_block`. PostgreSQL, staging, production, юридическое утверждение и публикация документов не проверены; `docs/legal/**` этим траншем не изменялись. Общая готовность остаётся **84%**; commit/push/deploy не выполнялись.
# P0-B: неизменяемый технический черновик — 02.10.2026

Локально добавлен канонический снимок принятой версии предложения со сторонами, предметом, событием/датой/слотом/составом, всеми денежными условиями и SHA-256. Подтверждения фиксируют actor/org/role/version/hash/effect; платёж и Deal Room требуют совпадающие неизменяемые записи обеих сторон. Персональный код хранится как salted PBKDF2 hash, действует 15 минут, одноразовый и имеет append-only reissue после expiry. Production требует SMTP, API показывает доставку отдельно по сторонам, а plaintext OTP не попадает в EmailOutbox/audit. Выпуск снимка и изменение состава сериализованы общей блокировкой Event; после выпуска состав закрыт до отдельного сценария изменения сделки. Deal Room показывает точный текст и историю и использует формулировку технического подтверждения до юридического sign-off. Подробности и доказательства: [CONTRACT_DRAFT_ACK_2026-10-02.md](ops/CONTRACT_DRAFT_ACK_2026-10-02.md).

Alembic: 40 ревизий, одна dirty-голова `ffbc123cd4e6`, manifest `draft/manual_block`. Расширенный P0-B набор **120 PASS, 6 SKIP**, финальный race-срез **51 PASS, 5 SKIP**, полный API **628 PASS, 9 SKIP**, web TypeScript/**17 unit-файлов, 72 теста**/production build и Playwright **1 PASS**. Независимый финальный review не нашёл конкретных P0/P1; остаётся P2 неатомарности synchronous SMTP/DB commit. Фактический PostgreSQL run, staging, production и юридическая сила не проверены. Общая готовность остаётся **84%**.

## 38. P0-E: защита отмены и маршрута возврата, локальный срез 02.10.2026

[Технический отчёт](ops/CANCELLATION_REFUND_GATES_2026-10-02.md): отмена удерживает Offer и строки Payment, сохраняет бронь/слот при любом денежном следе кроме failed; проверен поздний успешный webhook после отклонённой отмены. Возврат выбирает сохранённый provider/merchant, требует точного успешного результата адаптера и блокирует повтор во время processing и новый запрос после частичного возврата до утверждённого расчёта. Guard будущей выплаты учитывает статус брони, открытые возвраты и положительный нетто-остаток; endpoint выплат не включён. Финальный полный API **634 PASS, 9 SKIP**, Ruff, diff-check и source/deploy-payload secret gate PASS; промежуточный отказ нестабильного двухсекундного теста rate limiter устранён в ожидании теста. Независимый read-only review не нашёл новых конкретных P0/P1. Остаются P2 разрыв между внешним refund и DB commit, отсутствие PostgreSQL concurrent cancel/webhook теста, а также юридические и партнёрские решения по суммам и удержанию. Доступа к staging/production и live деньгам этот срез не даёт. Общая оценка **84%**; commit/push/deploy не выполнялись.

Дополнение P0-E: `processing` с audit намерения теперь коммитится до вызова refund адаптера. Второй commit записывает только проверенный ответ, денежное движение и итоговый статус; сбой между ответом и финализацией оставляет `processing` и блокирует повторный вызов. Отдельно сверяется `full|partial` с суммой. Полный API **636 PASS, 9 SKIP** до последней скалярной правки, адресный набор refund/payout/reconciliation/cancel после неё **56 PASS**. Независимый re-review не нашёл конкретных новых P0/P1/P2. Этот контур намеренно не переводит неоднозначный результат в `refunded`: для live требуются provider query, идемпотентное разрешение и операторская сверка. Подробности — в [отчёте](ops/CANCELLATION_REFUND_GATES_2026-10-02.md). Общая оценка **84%**.

# Помощник поддержки: точность срочности и handoff — 02.10.2026

Локально закрыты обнаруженные независимыми reviewer крайние случаи: короткий OTP и код с тире маскируются до записи/передачи, неявка исполнителя распознаёт естественные формулировки, завершённая неявка не сохраняет срочность, а раннее нерелевантное «не пришёл» больше не заслоняет причину срочного обращения в сокращённом handoff. Последний объединённый профильный набор поддержки **79 PASS**; Ruff, compileall и `git diff --check` PASS. Полный API suite **652 PASS, 9 SKIP** был до последней группы исправлений и не является полным доказательством итогового кода. Рабочий сценарий с реальным оператором, staging/production и доставка уведомлений не проверены. [Подробный handoff](ops/SUPPORT_ASSISTANT_TRIAGE_2026-10-02.md). Общая оценка остаётся **84,00%**; commit/push/deploy не выполнялись.

Дополнение: три типовые проблемы (срыв выступления до прибытия, сообщение о списании при ожидающей оплате брони, возможная двойная бронь) получают безопасный маршрут к человеку. Финальный профильный API набор **93 PASS**; локальный браузерный путь помощник → тикет → оператор → ответ → reopen на временной SQLite и отдельных портах **1 PASS** до этого последнего расширения классификации. Обычный Playwright config не использовался для этого прогона; новый изолированный config защищает общую БД, токены и Next cache. Полный API набор после расширения и staging/production не проверены. Общая оценка **84,00%**.

## Локальный Codex Security scan API — 02.10.2026

[Отчёт и очередь исправлений](ops/SECURITY_SCAN_2026-10-02.md): статически просмотрены 83/83 файла `booker_api`, оформлено 11 исходных находок (1 high с узкой предпосылкой, 10 medium). Первый узкий фикс — TOTP step-up для списка заявок на площадку — локально проверен `test_trust_outbox.py` + `test_totp_security.py`, **11 PASS**. Остальные находки пока открыты, включая восстановление пароля, публичность исследовательских карточек/занятых слотов/медиа, iCal, первое освобождение от комиссии и независимые блоки выплат. Отчёт плагина содержит ошибочные двойные префиксы путей; корректные пути указаны в локальном отчёте. Production, PostgreSQL и динамическая эксплуатация не проверены; общая готовность **84,00%**, commit/push/deploy не выполнялись.

Дополнение: iCal теперь ограничен до JSON-разбора на маршруте импорта, до парсинга inline и при потоковом чтении внешнего ответа; gzip/deflate сохраняются с ограничением распакованного размера, число событий ограничено 5000. Профильный iCal + attachment набор **37 PASS**, Ruff/compileall/diff-check PASS; полная API suite после этой правки ещё не запускалась. Это локальный фикс без production проверки; статус исходного immutable scan остаётся историческим.

## Актуальный срез S05/S06 и параллельной работы · 02.10.2026

Измеримый реестр [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md) теперь показывает **55,00%**: S05 закрыт локально (+3,00 п.п.; осталось 45,00 п.п.). Исследовательский API закрыт для гостя, публичные профили скрывают занятые интервалы и неаттестованные фотографии, смена источника **или** прав фото при импорте снимает прежнюю аттестацию, поиск площадки считает открытые слоты отдельно по каждому залу. Профильный API набор **43 PASS**, изолированный browser набор **5 PASS**, web lint/build и отдельные **4 PASS** предпросмотра чернового профиля, Ruff/diff-check PASS. Независимый reviewer не нашёл новых P0/P1/P2 в финальных исправлениях. Точный отчёт — [PUBLIC_CATALOG_PRIVACY_2026-10-02.md](ops/PUBLIC_CATALOG_PRIVACY_2026-10-02.md). После совместных S06 правок полный API suite **692 PASS, 9 SKIP**; staging, реальные права на фото и production не проверены.

S06 остаётся открытым. Первый admin может настроить TOTP до получения административного bearer через пароль, одноразовый SMTP proof и код приложения; email не заменяет уже включённый TOTP. Старые reset-ссылки в EmailOutbox очищаются при старте, новая отправка не хранит секрет. Исправлены путь web-админки и форма входа/сброса; адресный backend набор **30 PASS**, изолированный web browser **4 PASS**, TypeScript и unit PASS. Отдельный [отчёт](ops/ADMIN_TOTP_BOOTSTRAP_2026-10-02.md) фиксирует оставшиеся gate: независимый порядок восстановления потерянного устройства, подтверждение владения email, фактический SMTP и staging/production. Отдельный существующий чат «Букер — admin reconciliation» выполнил read-only аудит S06. Новые worktree-чаты для дизайна и schema gate были запрошены, но их готовый thread ID и рабочая среда на этом срезе не подтверждены. Общий dirty checkout сохраняется, commit/push/deploy/SSH не выполнялись.

Обновление P07 на 02.10.2026: `GET /catalog/search-page` и последовательная дозагрузка web работают локально, старый маршрут сохранён. Пакетный publication gate сохраняет те же проверки по сравнению с одиночным; 38 адресных API PASS. Синтетические 150 профилей прошли 7 страниц без повторов, запросов на страницу 24 карточек: 6 для артистов, 10 для площадок на SQLite. Web TypeScript/Next build и browser поиск 5 PASS; 390 px browser 4 PASS. Подробности и оставшиеся измерения в [CATALOG_PERFORMANCE_PLAN_2026-10-02.md](ops/CATALOG_PERFORMANCE_PLAN_2026-10-02.md). **P07 открыт**, реальная мобильная сеть/медиа и staging p95 не измерены; счёт остаётся **55,00%**.

Обновление S06 после email proof: локальная миграция `a01d23e45f67` и web-путь подтверждения адреса добавлены в общий dirty checkout. Новые учётные записи при включённом gate не получают новые организационные права до подтверждения; историческим email не проставляется фиктивная проверка. Прямое SQL-назначение нового администратора без `email_verified_at` блокируют SQLite runtime/Alembic и PostgreSQL migration trigger; синтетические тестовые администраторы получили явную тестовую отметку, demo seed — только локальный. Адресный API 67 PASS, schema/Alembic/email после legacy-adoption теста 37 PASS/1 SKIP, изолированный browser email 1 PASS, web TypeScript/17 unit-файлов/Next build PASS. Финальный полный API прогон на этом локальном снимке: **711 PASS, 9 SKIP** за 196 секунд. Дополнительный отчёт — [ADMIN_TOTP_BOOTSTRAP_2026-10-02.md](ops/ADMIN_TOTP_BOOTSTRAP_2026-10-02.md). **S06 открыт**: самостоятельное восстановление потерянного TOTP остаётся закрытым; нужен независимый утверждённый офлайн-процесс, реальная SMTP/миграция/staging-проверка. Общий счёт **55,00%**.

Независимый S06 review нашёл два P2: чужой неподтверждённый email может быть зарезервирован до письма, а TOTP секрет сохраняется в БД без шифрования. Их нельзя считать закрытыми полным API набором. Automatic approval review дважды отклонял изменение secret-scanner/deploy exclusions как возможное ослабление защиты. После явного разрешения владельца изменены только исключения незакоммиченных `apps/web/.next-e2e-*`/`.next-preview-*` и allowlist хешей двух фиксированных тестовых TOTP-значений. Объединённый source/build/deploy-payload gate затем **PASS**; его 14 профильных regression тестов, Ruff и diff-check PASS. O04 всё ещё открыт: точный кандидат/CI/security и staging не доказаны.

Дополнительный локальный агент поддержки исправил позднюю неявку после разрешённой ранней и сохранение актуального платежного вопроса в handoff. Профильный support API набор **83 PASS**, дополнительный secret/support набор **14 PASS**, изолированный browser support **1 PASS** после правок, Ruff/scoped diff-check PASS; общий API **711 PASS/9 SKIP** выполнен до этого последнего support diff. Не утверждается production доставка человеку. [SUPPORT_ASSISTANT_TRIAGE_2026-10-02.md](ops/SUPPORT_ASSISTANT_TRIAGE_2026-10-02.md) фиксирует границы. Общий счёт **55,00%**.

Решение владельца для дежурства: Павел получает отдельный кабинет оператора поддержки с меньшими правами, чем администратор. Локально добавлены роль `is_support_operator`, серверный TOTP step-up только для очереди `/admin/support/tickets*`, назначение/отзыв роли подтверждённому email администратором, отзыв старых сессий и SQLite/PostgreSQL migration guard. Назначение на аккаунт с членством в организации и добавление оператора в организацию блокируются; точный route allowlist, каталог с необязательным токеном и SSE сделки не дают обойти служебную границу. Новая ревизия `a02e34f56a78` после `a01d23e45f67`; draft manifest содержит 42 ревизии и остаётся `manual_block`. Адресный backend role/queue/schema/Alembic набор **31 PASS, 1 SKIP**, финальный полный API suite **716 PASS, 9 SKIP**; Ruff/manifest/diff/secret gate PASS. Два агента добавили отдельный `/operator` и admin-управление ролью в непересекающихся web-файлах. Изолированный browser **4 PASS**, включая настоящий backend grant/revoke и ответ заказчику; web TypeScript и финальная Next build PASS. Независимый read-only reviewer после закрытия найденных P1/P2 не нашёл конкретных P0/P1/P2. Email аккаунта Павла, запасной дежурный и канал сигнала не определены; реальный доступ/доставка и PostgreSQL/staging/production не проверены. Уже засчитанный P05 повторно не оценивается: **55,00%**.

## 42. Защита секретов поддержки и обязательная 2FA, локальный срез 02.10.2026

В общем dirty checkout на HEAD `fbb41f5` закрыт найденный путь сохранения Bearer-кода с `+`, `/`, `=` в истории помощника и тикете. `support_agent.py` скрывает значение до записи, регрессия проверяет ответ, exchange, тикет и сообщение оператору. Старые отрицательные тесты служебной 2FA адаптированы к действительной семантике: сессия после входа с TOTP уже подтверждена; токен до повышения роли остаётся без step-up. Затронутый набор **153 PASS/1 SKIP**, полный API **722 PASS/9 SKIP**, Ruff, diff-check и source/build/deploy-payload secret gate PASS. Отчёт: [SUPPORT_ASSISTANT_TRIAGE_2026-10-02.md](ops/SUPPORT_ASSISTANT_TRIAGE_2026-10-02.md). Изолированный browser после этой backend-правки, PostgreSQL, staging, production и фактическая доставка не проверены. Три шкалы неизменны: полный запуск **55,00%**, технический MVP **46,00%**, дизайн **15,00%**.

Ближайший S06: реализовать одноразовый offline recovery kit для обязательной служебной 2FA без mailbox-only сброса, затем проверить миграцию на копии фактической БД, реальный SMTP и staging. Модель `User.totp_secret` пока хранит Base32 открыто; шифрование с управлением ключом остаётся отдельным gate. Общая dirty-цепочка миграций имеет 42 ревизии и draft `manual_block`; производство не обновлялось. Commit, push, deploy не выполнялись.


## 43. Offline recovery служебного доступа — локально завершён, 02.10.2026

HEAD `fbb41f5` плюс общий dirty diff. Резервные коды для оператора/единственного администратора, одноразовое восстановление с новым TOTP, отзыв сессий и комплектов, профиль и pre-login UI проверены. Полный API **725 PASS/9 SKIP**, адресный API/schema **54 PASS/1 SKIP**; браузерный сквозной путь через настоящий API и временную SQLite на 390px **1 PASS**. Отдельные auth UI сценарии прошли 4+1 тестами; последний запущенный до прерывания процесс завершился успешно, не был перезапущен без проверки. Web unit **17 PASS**, финальная Next build/typecheck, Ruff и source/deploy secret gate PASS. Исправлены allowlist счётчика оператора и вход администратора без организации.

Актуальная цепочка: **43 ревизии**, head `a03f45a67b89`, draft `manual_block`. [Отчёт и границы](ops/STAFF_RECOVERY_2026-10-02.md). S06 остаётся открытым: двухстороннее утверждение при нескольких администраторах, security notifications/реальная почта, шифрование TOTP, rollout email и фактической БД/staging. Общая **55,00%**, MVP **46,00%**, дизайн **15,00%**, изменение 0,00 п.п. Recovery зависит от других незакоммиченных auth/schema частей; неполный коммит не создан. Следующий шаг — совместимый кандидат и PR/CI. Без агентов, commit/push/deploy/SSH.

## 44. Изолированная ветка поддержки, 03.10.2026

В `codex/booker-support-acceptance-20261002` локально проверены маршрутизация
новых обращений, скрытие резервных кодов в новых и исторических ответах,
handoff после повторных уточнений и read-only статус связанной брони из Deal
Room. Общий dirty checkout не перезаписывался. После уточнения двух старых
ожиданий приоритета полный API suite **779 PASS/9 SKIP**; браузерный файл
поддержки **3 PASS** на изолированной SQLite, включая реальную тестовую бронь
и 404 для постороннего аккаунта. TypeScript/Next build, Ruff и source/payload
secret gate прошли в затронутых срезах. Отчёт —
[SUPPORT_BOOKING_CONTEXT_2026-10-03.md](ops/SUPPORT_BOOKING_CONTEXT_2026-10-03.md).

По актуальному `docs/PROJECT_PROGRESS.md` общего checkout полный запуск
**59,00%**, MVP **56,00%**, дизайн **15,00%**; +0,00 п.п. за этот срез,
поскольку P05 уже был засчитан. PostgreSQL, staging, production, реальный
адресат и доставка, очистка исторических секретов в БД/backup и юридические
платёжные gates остаются открытыми. Push и deploy этой ветки не выполнялись.

## 45. Единый аккаунт, локальный этап A1, 03.10.2026

В отдельном worktree добавлены модель и миграция `user_identities` после
`a08f90e12f34`, с уникальной парой провайдер/subject и без автоматического
объединения по email. Старые `users`, пароль и сессии остаются в прежней схеме;
новый внешний вход пока не включён. Read-only локальная БД не является
staging/production. Точный состав, тесты, ограничения A2 и rollback:
[IDENTITY_MODEL_STAGE_A1_2026-10-03.md](ops/IDENTITY_MODEL_STAGE_A1_2026-10-03.md).

Три шкалы остаются **59,00% / 56,00% / 15,00%** (+0,00 п.п.): этап A1 ещё не
закрывает единый внешний вход и не проходит фактический migration/staging gate.

## 46. Подготовка к необязательным credentials, этап A2a, 03.10.2026

API теперь отклоняет локальный пароль, если у аккаунта нет `password_hash`, и
не создаёт служебный email без адреса, сохраняя внутреннее уведомление. Проверка
приглашения также явно отвергает аккаунт без email. Затронутые auth/notification
тесты: 35 PASS; Ruff, diff-check и secret gate прошли. Поля `users.email` и
`users.password_hash` в действующей схеме всё ещё обязательны: это подготовка,
не внешний вход. Следующая миграция требует отдельной SQLite-репетиции с
сохранением триггеров, nullable-проекции в web и source/staging gate. Шкалы
не меняются; изменений в production нет.

## 47. Необязательные credentials, локальный этап A2, 03.10.2026

Кодовый SHA `39900f474970d008b829e6fbc42d967dc94d5788` в отдельном
worktree. Добавлена миграция `a10f12e34f56` с nullable email и
паролем, сохранением SQLite-триггеров и FK-состояния; API/web принимают
`email: null` без ложного подтверждения. Репетиция копии SQLite и затронутые
тесты описаны в [IDENTITY_MODEL_STAGE_A2_2026-10-03.md](ops/IDENTITY_MODEL_STAGE_A2_2026-10-03.md).
Manifest остаётся `manual_block`, PG/staging/production не проверены, OAuth
пока не включён. Полный API **787 PASS/9 SKIP**, schema/Alembic
**35 PASS/1 SKIP**, web TypeScript/21 unit/build PASS; Ruff и secret gate PASS.
Три шкалы **59,00% / 56,00% / 15,00%** (+0,00 п.п.).

## 48. Telegram initData, локальный этап A3a, 03.10.2026

Кодовый SHA `99d42dadbeec1ddd204c4c2a2da468dd73abea93`: добавлен
серверный HMAC-валидатор без маршрута входа и выдачи сессии.
Подделка, дубликат полей, устаревшие данные и неверный Telegram ID отклоняются;
адресные тесты 9 PASS, Ruff и secret gate PASS. Детали и отсутствующие
pending-auth/legal/TOTP gates — в
[TELEGRAM_INITDATA_STAGE_A3A_2026-10-03.md](ops/TELEGRAM_INITDATA_STAGE_A3A_2026-10-03.md).
Три шкалы остаются **59,00% / 56,00% / 15,00%** (+0,00 п.п.).

## 49. Одноразовый Telegram pending-auth, локальный этап A3b, 03.10.2026

После проверки `AGENTS.md`, `CONTRACT.md`, `DEVELOPMENT_GOAL.md`, реестра
прогресса и чистоты изолированной ветки добавлены два серверных маршрута:
подготовка подписанного Mini App proof без сессии и одноразовое завершение.
Первый вход привязан к точному legal pack и отдельным согласиям; уже связанный
аккаунт входит без объединения по email, служебная роль требует Booker TOTP.
Таблица `pending_external_auth` и миграция `a11f23e45f67` записывают только
хеши proof/token; schema manifest остаётся `manual_block`. Кодовый SHA
`72934af4eeb7624b12913ca6de6a0cbc20f3e1b7`; полный API **802 PASS,
9 SKIP**, адресный suite **38 PASS, 1 SKIP**, Ruff/secret/diff PASS. Подробности — в
[TELEGRAM_PENDING_AUTH_STAGE_A3B_2026-10-03.md](ops/TELEGRAM_PENDING_AUTH_STAGE_A3B_2026-10-03.md).

Staging bot, Mini App/web, явная привязка аккаунта и onboarding по ролям ещё
не проверены. Полный запуск **59,00%**, MVP **56,00%**, дизайн **15,00%**,
изменение каждой шкалы +0,00 п.п.

## 50. Явная привязка Telegram к Booker, локальный этап A3c, 03.10.2026

Сверены текущая ветка, продуктовый контракт, расширенная цель по идентичности,
сессии и операторский allowlist. Добавлены просмотр собственных способов
входа, явная привязка Telegram по одноразовому proof с повторным паролем и
staff TOTP, безопасная отвязка с проверкой оставшегося email+password входа,
отзывом других сессий, audit и статическим security notice. Чужой subject и
второй Telegram ID не присваиваются. Кодовый SHA
`926f53e3874a38c18c495b8e274ebd027249215d`, отдельный фикс
календарной тестовой даты `238b81895485d3f0923999b2217d91c3180d5ecc`.
Полный локальный API **808 PASS, 9 SKIP**, адресный identity/ACL **47 PASS**;
Ruff, secret gate и diff-check PASS. Подробности — в
[TELEGRAM_ACCOUNT_LINK_STAGE_A3C_2026-10-03.md](ops/TELEGRAM_ACCOUNT_LINK_STAGE_A3C_2026-10-03.md).

Это локальный API-срез; web/Mini App, внешние-only step-up, Яндекс/VK и
staging остаются открытыми. Полный запуск **59,00%**, MVP **56,00%**, дизайн
**15,00%**; изменение +0,00 п.п. по каждой шкале.

## 51. Telegram Mini App web-вход, локальный этап A3d, 03.10.2026

Перед этапом сверены `AGENTS.md`, продуктовый контракт, расширенная цель,
реестр `PROJECT_PROGRESS.md`, этот журнал и чистота изолированной ветки.
Кодовый SHA `dcafeb29f85eed89068635c2b74be676cf269964` добавил страницу
`/telegram`, официальный Telegram JS, серверный prepare/complete, точный
legal pack при первом входе, Booker TOTP для staff и локальный onboarding
трёх пользовательских ролей. CSP допускает только Telegram script origin.
Playwright на временной SQLite/loopback/production build — **3 PASS**;
статический perimeter — **3 PASS**; web lint/21 unit/build, source/build/deploy
secret gate и diff-check — PASS. Подробности и границы:
[TELEGRAM_MINIAPP_WEB_STAGE_A3D_2026-10-03.md](ops/TELEGRAM_MINIAPP_WEB_STAGE_A3D_2026-10-03.md).

Реальный bot/WebView и staging не проверены. Для нового аккаунта без email
staging/production gate подтверждённой почты ещё не даёт создать организацию;
это следующий интеграционный этап. Полный запуск **59,00%** (осталось 41,00
п.п.), MVP **56,00%** (осталось 44,00 п.п.), дизайн **15,00%** (осталось
85,00 п.п.), изменение каждой шкалы **+0,00 п.п.** Общий dirty checkout,
production и внешние секреты не менялись.
