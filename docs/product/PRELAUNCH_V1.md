# Prelaunch commercial v1 — журнал реализации и приёмки

OWNER DIRECTIVE 2026-09-12: preparation for commercial launch and monetization.

Статус: **в работе**. Этот документ не подтверждает готовность запуска.
Полный объём — разделы 0–35 задания владельца от 2026-09-12.

## Исходное состояние, 2026-09-12

- `origin/master`, проверенный через fetch: `ca20ac2`.
- База рабочей ветки: `834fb22`; содержит master, действующий lime-дизайн
  и модерацию каталога площадок. Сохраняем эти изменения.
- Ветка: `feat/prelaunch-commercial-v1`; отдельный worktree
  `outputs/prelaunch-commercial-worktree`. Незакоммиченные изменения исходного
  каталога не входят в эту задачу и не переносятся.
- API: FastAPI, SQLAlchemy, Alembic; web: Next 15 / React 19.
- Уже есть: Organization/TeamMember RBAC, EventTeamRequirement, версия оффера
  и quote_id, ack, защищённый hold, Deal Room, договор, payment adapter,
  public briefs/response, favorites/compare/shared shortlist, saved searches,
  отзывы Completed, replacement, in-app/email abstraction, append-only audit.
- Старый DELIVERY_GAP_ANALYSIS датирован 2026-09-06 и ошибочно отмечает часть
  перечисленных реализованных функций отсутствующими. Он не является доказательством.
- Коммерческих plans/subscriptions/billing orders/paid campaigns нет.
  Текущий pricing использует 10% и льготу первой сделки; v3 должен явно
  заменить политику новых офферов и сохранить старые снимки.
- Growth, server matching/compatibility/readiness/budget и Business предстоит
  реализовать; текущие event next steps выводятся на клиенте.
- Публичный профиль артиста пока выдаёт примерное время ответа текстом;
  требуются измеренные факты или неизвестное значение.
- В CI уже есть API, web и критические Playwright на PR; расширить коммерцией.
- Юридический пакет остаётся черновиком; provider boundary допустим,
  реальные платежи/production/DNS/merge запрещены этой задачей.

## Последовательность и критерии доказательства

- [ ] 1–4, 6: Contract v3, catalog, models/migration, providers, fees/entitlements.
- [ ] 5, 8, 22: pricing, кабинеты, admin commercial center.
- [ ] 7, 9–11: promotion ranking/attribution, Growth, Opportunities, EPK.
- [ ] 12–20: matching, compare, compatibility, readiness, budget, collaboration,
  repeat, replacement, Business.
- [ ] 21, 23–28: notifications, analytics, SEO/trust/security, mobile/states/flags.
- [ ] 29–31: API coverage, все именованные E2E desktop/390, CI и build.
- [ ] 32–35: документация, provider handoff, аудит каждого требования и отчёт.

Для каждого пункта нужны конкретные UI/API/DB/auth/audit/tests и состояния
loading/empty/error, где применимо. Наличие страницы или зелёный узкий тест
не подтверждает весь пункт. Все непроверенные требования остаются открытыми.

## Проверки

- Исходный `make test-api PYTHON=/home/art67/booker/.venv/bin/python`:
  не запущен — GNU make отсутствует в PATH. Запущен эквивалент
  `cd apps/api && /home/art67/booker/.venv/bin/python -m pytest -q`;
  результат будет записан после завершения.


## Коммерческое ядро — первый инкремент

Реализованы модели и migration `d9e0f1a2b3c4`, каталог/entitlements, disabled/stub
provider, заказы подписок, проверка webhook/идемпотентность, ручной admin grant,
версионированное изменение тарифов, отмена/выбор тарифа следующего периода,
Contract v3 и fee snapshots с DB immutability guard.
Это не закрывает целиком разделы 1–4/6: UI, promotion lifecycle, recurring
integration acceptance и общая приёмка ещё впереди.

Проверки на исправном Python 3.12.14 в отдельном `.venv`:

- Исходный SHA `834fb22`, извлечённый в `/tmp/booker-prelaunch-baseline`:
  `python -m pytest -q` — **203 passed, 2 skipped** (32.48s).
- Текущая ветка: `cd apps/api && ../../.venv/bin/python -m pytest -q` —
  **228 passed, 2 skipped** (36.68s). Включает 25 новых parametrized API cases
  и upgrade/downgrade с историческим оффером. Два skip относятся к исходному suite.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- Node 24.19.0 / npm 10.9.3 и GNU make подготовлены локально; системная среда
  не изменялась. Старый venv не используется из-за отсутствующего libssl 1.1.
- PostgreSQL runtime и браузерная приёмка этого инкремента пока не проверены.

## Pricing и управление тарифом

Первый core commit: `50a66cd`.

Добавлены `/pricing`, `/cabinet/performer/growth`, `/cabinet/venue/growth`,
`/cabinet/customer/business`: текущий тариф, будущая отмена/изменение, история
заказов, тестовая оплата и недоступная оплата. Growth и Business здесь пока
содержат коммерческую секцию; аналитика и профессиональные инструменты ещё
не приняты. Все цены, проценты и годовая экономия получены из API.

Проверки:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` —
  **228 passed, 2 skipped** (35.20s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH npm run test:unit` — **42 passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 BOOKER_DATABASE_URL=sqlite:////tmp/booker-prelaunch-e2e.db BOOKER_ENVIRONMENT=test BOOKER_COMMERCE_PROVIDER=stub BOOKER_COMMERCE_ALLOW_STUB=true BOOKER_COMMERCE_WEBHOOK_SECRET=local-test-only-commerce-webhook-secret npx --prefix apps/web playwright test --config apps/web/playwright.config.ts apps/web/e2e/commercial.spec.ts --workers=1 --reporter=line`
  — **7 passed** (7.2s), E-COM-01–04 на 1440 и 390, error recovery.
- Скриншоты pricing из Playwright визуально просмотрены (1440 и 390):
  нет горизонтального переполнения, карточки и FAQ читаются. Выделение выбранного
  audience/периода усилено цветом lime общей дизайн-системы.
- In-app Browser дважды вернул ERR_SOCKS_CONNECTION_FAILED для локального сервера;
  это ограничение среды. HTTP 200 и browser E2E подтверждены через Playwright.

CI расширен коммерческим suite с явно test-only provider настройками.
Production/merge/live payments не выполнялись. Цель остаётся в работе.

## Продвижение — третий инкремент

Реализованы оплаченные и включённые кампании, квоты, завершение/остановка,
фильтрация перед платной вставкой, ограничение доли и маркировка. Кабинет показывает
показы, переходы, CTR, заявки и Confirmed бронирования. История заказов обновляется
после изменения кампании. Admin API версионирует цены продвижения; существующие
заказы сохраняют snapshot. Миграция `e0f1a2b3c4d5` добавляет credit ledger и attribution.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **238 passed, 2 skipped** (47.75s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/commercial.spec.ts e2e/promotions.spec.ts e2e/search-filters.spec.ts e2e/supply-nav.spec.ts --workers=1 --reporter=line`
  — **14 passed** (20.7s). E-COM-01–07 на desktop/390. Изолированный API настроен
  на test/stub, как в предыдущем инкременте. Production не используется.
- API отдельно проверяет 20% cap, отсутствие соседних вставок, сохранение organic_rank,
  busy/city/category/budget exclusion, idempotency, чужую организацию/профиль,
  credit limits, Featured entitlement, synthetic/unclaimed/unpublished venues,
  expiry и полный attributed request → offer → ack → hold → contract → payment → Confirmed.
- Скриншоты каталога и кабинета из Playwright визуально просмотрены. Поправлены
  устаревшие селекторы главной в существующем E2E; продуктовые условия не ослаблены.

Growth Center, Opportunities, EPK, Decision Engine и остальные пункты полного
задания остаются в работе. Это промежуточная приёмка, не готовность запуска.

## Growth Center — четвёртый инкремент

Добавлены `growth/service.py`, `/organizations/{org_id}/growth`, Premium CSV export,
`/discovery/signals`, `/requests/{id}/loss-reason`, миграция `f1a2b3c4d5e6`.
Интерфейс работает в обоих supply-кабинетах: воронка, периоды, профиль, гонорары,
время первого предложения, свободные даты, подсказки, причины потерь и benchmark.
В закрытом Deal Room участник может явно отметить причину; у customer есть price.
Старый примерный ответ «в пилоте обычно за пару часов» удалён. Публичный счётчик
«завершённых сделок» теперь учитывает только Completed, что проверено полным
payment → check-in → check-out. Крупный остаток master task сохраняется.

Проверки:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **244 passed, 2 skipped** (56.94s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/growth.spec.ts e2e/commercial.spec.ts e2e/promotions.spec.ts --workers=1 --reporter=line`
  — **11 passed** (28.1s). E-GROWTH-01 на 1440/390 с реальным гостевым браузером,
  server favorite/request и проверкой 90d после Pro. Мобильный screenshot просмотрен.
- Последующая точечная проверка московской границы суток и счётчика Completed:
  `.venv/bin/python -m pytest -q apps/api/tests/test_growth.py apps/api/tests/test_pilot_closure.py`.

Правила расчёта и ограничения наблюдений раскрыты в UI и `ANALYTICS.md`.
Метрики не подменяют подтверждения оплаты или выплаты. Production не затрагивался.

Точечная проверка границы суток и Completed — **8 passed**. Дополнительный
`npx --prefix apps/web playwright test --config apps/web/playwright.config.ts apps/web/e2e/growth.spec.ts --workers=1 --reporter=line`
с теми же BOOKER_API_URL/BOOKER_WEB_URL — **3 passed** (8.5s), включая восстановление
после ошибки API. Финальные lint и web-lint — passed.

## UTC и защита календаря

При реализации Opportunities обнаружено: SQLite `DateTime(timezone=True)` теряет
смещение входного времени. Это могло превратить `18:00+03:00` и `15:00Z` в разные
моменты при проверке пересечений. `UTCDateTime` нормализует все новые значения
перед записью и возвращает aware UTC при чтении. Физическая схема не меняется.
Исторические naive значения сохраняют прежнее толкование UTC; история не переписана.

Исправление проверено отдельно от незакоммиченного Opportunities: архив `c131c2d`
в `/tmp/booker-timezone-isolation` плюс только UTC type/model import и тесты.
`/home/art67/booker/outputs/prelaunch-commercial-worktree/.venv/bin/python -m pytest -q tests/test_datetime_type.py tests/test_alembic.py`
из изолированного `apps/api` — **6 passed** (1.02s). Проверены roundtrip +03:00,
409 для второго слота в тот же момент в UTC, busy overlay с другим offset и миграции.
Полный текущий API-набор вместе с Opportunities — **251 passed, 2 skipped** (45.98s).

## Opportunities

Добавлены supply-ленты `/cabinet/performer/opportunities` и
`/cabinet/venue/opportunities`, публикация дат/публичного бюджета/требований на
`/briefs`, ручной отклик с выбранным собственным профилем и чтение откликов
заказчиком с переходом к профилю. Отклик не создаёт OfferVersion или бронь.
Миграция `a2b3c4d5e6f7_opportunities` хранит явный публичный снимок брифа,
выбранный профиль отклика, личные сохранённые фильтры и дедупликацию уведомлений.

API: `GET /organizations/{id}/opportunities`,
`GET/POST /organizations/{id}/opportunity-filters`,
`DELETE /opportunity-filters/{id}`; расширены существующие `/briefs` и responses.
Free получает тот же подбор, что Pro/Premium; платные функции — расширенные
фильтры и сохранённый поиск. Уведомления только in-app, после отдельного согласия;
при истечении подписки не отправляются, отзыв согласия остаётся доступен.
Бюджет частного Event никогда автоматически не публикуется.

Скоринг детерминирован: категория 25, дата 30, география 20, известный бюджет 15,
известные технические требования 10. Unknown не даёт баллы. Несовпадение категории,
города без разрешённого выезда, занятая дата, известный недостаточный бюджет или
оборудование исключают профиль. Площадка требует опубликованного claimed-профиля,
календаря владельца и достаточной вместимости. Для «200+» точное число гостей
неизвестно и требует согласования. Процент не является вероятностью сделки.

Проверки:

- `.venv/bin/python -m pytest -q apps/api/tests/test_opportunities.py` — **6 passed** (1.74s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/opportunities.spec.ts e2e/supply-nav.spec.ts e2e/growth.spec.ts --workers=1 --reporter=line`
  — **7 passed** (20.3s), включая E-OPP-01/02 desktop/390 и чтение отклика.
  Мобильный screenshot просмотрен; горизонтального переполнения нет.

EPK и разделы Decision Engine/Business/общей приёмки остаются в работе.

Полный API после проверки вместимости Opportunities:
`PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` —
**252 passed, 2 skipped** (44.97s).

## Защита booking payment

Фактически обнаружены старые пробелы: provider=stub по умолчанию, отсутствие
object auth перед checkout/replay, повторные платежи одной брони, late failed
после captured и неподтверждённое владение резервом при capture. Исправлены:
fail-closed default и тройной stub gate; customer writer authorization; сериализация
и повтор одного Payment на booking; scope ключа; монотонные подтверждения;
consumed hold; поздняя оплата не подтверждает истёкший резерв. Условия оффера
фиксируются уже при удержании даты, до подписания договора.

Deal Room получает server capabilities и явные русские состояния оплаты;
неподключённый provider не создаёт фиктивного успеха. Stub отмечен как тест без
списания денег. Управление оплатой доступно во вкладке «Платежи» на mobile/desktop.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **262 passed, 2 skipped** (55.69s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- Новый `test_payment_guards.py`: production/opt-in, fresh/replayed IDOR,
  read-only role, один checkout, out-of-order webhook, consumed hold,
  поздняя оплата и неизменность цены после hold.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/booking-payment.spec.ts e2e/deal-path.spec.ts --workers=1 --reporter=line`
  — **6 passed** (9.1s). Реальные локальные ack → hold → in-app OTP → подписи →
  Payment → тестовый capture на 1440/390; недоступный UI проверен отдельной fixture,
  production API gate — настоящими API-тестами. Screenshot 390 просмотрен.
  Обнаруженная скрытая на mobile кнопка перенесена во вкладку платежей.
- При повторном прогоне стенд вернул 429 после предыдущих регистраций. Чистый
  перезапуск изолированного API дал указанный результат без изменения prod limits.
  CI/Playwright могут задать `BOOKER_TEST_AUTH_RATE_LIMIT=1000`; действует только
  при environment=test. Production всегда сохраняет 20 auth-запросов за 5 минут.

## EPK / публичная витрина артиста

Миграция `b3c4d5e6f7a8_artist_presentation`, модель ArtistPresentation,
`GET/PUT /artists/{id}/presentation` и `/cabinet/performer/presentation`.
Редактор сохраняет обложку, видео, галерею, аудио/видеоссылки, программу, жанры,
формат/состав, длительность, географию и технические факты с явным unknown.
Owner/admin/manager пишут, viewer читает; чужая организация не получает доступ.
Версии защищают от потери конкурентной правки; одинаковый PUT идемпотентен.

Публичный `/artists/{id}` показывает эти данные, пакеты с длительностью и
ориентиром цены, реальные completed/response/reviews, избранное, выбор сравнения,
share и заявку. OG/description учитывают фактическую обложку/формат. Free остаётся
полноценным; расширенные лимиты возвращает API, данные не удаляются при expiry.
HTTPS validation не допускает javascript/local/private-IP/password URL, сервер
не загружает произвольные внешние материалы. Тестовые изображения E2E явно
помечены и существуют только в browser fixture.

Отзывы исправлены с org-wide на конкретный профиль/Completed. В публичном
календаре busy/held/confirmed overlays учитываются вместе с буферами. В базе
исходные open slots сохраняются; тесты iCal/vacation проверяют DB сохранность и
отдельно публичную недоступность. Очистка отпуска восстанавливает открытый слот.
Тарифы валидируют целые неотрицательные RUB/длительность, не меняют старые quotes.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **273 passed, 2 skipped** (56.56s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `test_presentation.py`: Free completeness, repeat/conflict, IDOR/viewer,
  media rights + unsafe URLs, Pro→expired retention/caps, immutable quote/trust,
  календарь/невалидные тарифы и отсутствие чужой репутации.

Пункт сравнения здесь даёт выбор профилей и переход в существующий `/compare`;
полное Compare V2 принимается следующим инкрементом. Остальной master task открыт.

- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/artist-presentation.spec.ts e2e/growth.spec.ts e2e/supply-nav.spec.ts --workers=1 --reporter=line`
  — **8 passed** (18.9s): сохранение/повторная загрузка/публичная витрина на
  desktop/390, восстановление после ошибки профиля, Growth и supply navigation.
  Screenshot 390 визуально проверен, горизонтального переполнения нет.

## Совместимость артиста, события и зала

Миграция `c4d5e6f7a8b9_hall_technical`, модель HallTechnicalProfile.
API: `POST /compatibility`, `GET /organizations/{id}/technical-halls`,
`GET/PUT /halls/{id}/technical`. UI: `/compatibility`,
`/cabinet/venue/technical`, ссылки из публичных профилей.

Сервер проверяет десять параметров: географию, вместимость выбранного зала,
полное временное окно, монтаж/демонтаж с busy overlays, сцену, мощность, звук,
микрофоны, обязательное оборудование за вычетом привозимого артистом и ограничения.
Unknown виден отдельно и не даёт положительных баллов. Процент — доля совпавших
проверок по данным участников, не вероятность и не гарантия. Synthetic calendar
и незаявленные технические факты не подтверждают совместимость. При нескольких
залах нужен явный выбор. Названия оборудования сравниваются точно без регистра.

Контекст события требует membership, берёт фактические город/гостей/начало из DB
и разрешает собственные подтверждённые слоты либо живые holds. Публичный запрос
такого исключения не получает; просроченный hold его теряет. Нельзя подставить
список собственных слотов с клиента. Writer редактирует свои залы, viewer читает;
версия/идемпотентный повтор защищают правки. Вместимость площадки обновляется
по максимуму залов. Изменение техники не меняет verified, тариф или quote.

Проверки:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **283 passed, 2 skipped** (59.30s).
- `test_compatibility.py` — **10 passed**, включая IDOR/viewer, unknown,
  отсутствие DJ-пульта, busy только во время монтажа, живой/истёкший собственный
  hold, unpublished/synthetic venue, несколько залов и неизменность score от Premium.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — **passed**.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — **passed**.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/compatibility.spec.ts e2e/artist-presentation.spec.ts e2e/booking-payment.spec.ts --workers=1 --reporter=line`
  — **8 passed** (19.4s). E-CUST-04 проходит unknown → заполнение владельцем →
  совместимо → удаление обязательного пульта → несовместимо на 1440/390.
  Исправлено обнаруженное переполнение формы из-за длинных option; mobile screenshot
  просмотрен. Сценарий включён в PR CI.

Decision Engine, Compare V2, readiness/budget и оставшиеся разделы master task
ещё не приняты. Этот инкремент не является общей готовностью к запуску.

## Ориентир стоимости Event Studio

Обнаружена и удалена клиентская формула `сумма × 1.28`. Новый
`POST /event-studio/estimate` считает диапазон только по опубликованным пакетам,
показывает источники/длительность, полный/частичный/неизвестный/пустой результат.
Скрытые площадки не раскрывают цены или названия; повтор ID не удваивает сумму.
Неизвестное не становится нулём. Результат — диапазон гонораров до сервисного
сбора, не OfferVersion, не гарантия цены/доступности; никаких длительностных
множителей. Для карточек catalog возвращает `honorarium_from_rub` с сервера.

В карте события — отмена устаревших запросов, загрузка, ошибка/повтор, явная
известная часть и объяснение метода. Удалено неподкреплённое сообщение, будто
карта уже проверяет совместимость всего состава.

- `test_event_planning.py` — 4 passed: точные диапазоны/источники, partial/unknown/0,
  hidden venue, входные лимиты и подмена цены, feature gate.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH npx tsx --test components/event-studio/adapter.test.ts` — 6 passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/studio-estimate.spec.ts --workers=1 --reporter=line` — 2 passed (8.1s),
  API tariffs → UI partial → публикация недостающего тарифа → full, плюс ошибка/повтор
  на 1440/390 без переполнения. PR CI включает сценарий.

Это основа серверных ориентиров. Три варианта smart matching и сохранение/бюджет
самого события принимаются отдельно и пока остаются открытыми.

Полный API после изменения ориентира: `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **287 passed, 2 skipped** (54.93s).

После визуальной проверки сводка на 390 px перестроена в одну колонку.
Повтор build — passed; тот же Playwright прогон — **2 passed** (7.3s).

## Сохранение события и повтор отправки

Миграция `d5e6f7a8b9c0_event_commands`: nullable Event.ends_at, Event.event_type
(историческое значение пустое), EventCommandReceipt. Existing budgets сохраняются.
`POST /events` теперь typed: валидирует окно, целые гости/бюджет, длины и размеры
состава. Пустое/некорректное тело возвращает стандартный validation 422 вместо
прежнего ручного 400. `GET /events` и `/events/{id}` возвращают новые поля;
подробный ответ включает объявленный budget_rub.

Опциональный `idempotency_key` у POST events/requests проверяется после writer
и object authorization. Строка организации/события сериализует команды; receipt
и доменные записи фиксируются одной DB-транзакцией. Одинаковый повтор возвращает
тот же ID; тот же ключ с другим телом — 409. Ключ в DB хешируется, scope включает
организацию или событие. Повтор не создаёт второй request.created/event.created.

Оба мастера отправляют ключи с учётом данных. Карта включает выбранные профили
в идентичность отправки и проверяет их актуальные категории. После частичной
ошибки повторяет создание и каждую выбранную заявку через server receipts;
старый browser result больше не считается доказательством полной отправки.
Черновик удаляется только после всех заявок. Офферы/брони автоматически не
создаются. Сетевой сбой не превращается в ложное сообщение о полной отправке.

Карта сохраняет budget и окончание, включая явный переход на следующий день.
Классический мастер даёт optional окончание и после отправки открывает событие.
Отсутствующая дата не подменяется сегодняшней. Страница события показывает
заданное окно/бюджет; неизвестное окончание остаётся неизвестным. Проверка
совместимости использует сохранённое окончание и не позволяет UI подменять его.

- `test_event_commands.py`, `test_alembic.py`, `test_event_requirements.py`,
  `test_workspace.py` — **19 passed** (2.57s). В том числе два параллельных
  HTTP create против файловой SQLite, replay/mismatch, IDOR/viewer, validation,
  восстановление после ошибки второго target и миграционный smoke.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **297 passed, 2 skipped** (62.44s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH npx tsx --test components/event-studio/adapter.test.ts` — **6 passed**.

Запросы без ключа сохраняют прежнюю семантику. Общая атомарная отправка всего
состава, три варианта matching/readiness/budget-summary и остальные разделы
master task не объявлены завершёнными этим исправлением. PostgreSQL concurrency
ещё требует отдельной фактической приёмки.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-command-retry.spec.ts e2e/studio-autosave.spec.ts e2e/studio-estimate.spec.ts e2e/compatibility.spec.ts --workers=1 --reporter=line`
  — **11 passed** (29.2s). Реальный API сохраняет вторую заявку, браузер получает
  503 вместо ответа, повтор оставляет один Event/два Request на desktop/390.
  Классический мастер сохраняет окончание и budget; проверены autosave/оффлайн,
  server estimate и совместимость. Прежний тест «browser cache предотвращает POST»
  заменён более сильной проверкой серверных записей после потерянного ответа.
- Ошибки validation в мастерах не печатают backend input/JSON; русское сообщение
  предлагает проверить поля. `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH npx tsx --test components/event-studio/adapter.test.ts lib/eventCommands.test.ts`
  — **8 passed**; после этой правки web-lint/build также passed.

Финальная регрессия после обработки validation: тот же Playwright с
`e2e/event-command-retry.spec.ts e2e/studio-autosave.spec.ts` — **7 passed** (11.9s).


## Smart Event Matching и предварительный состав

После обоих мастеров на `/events/{id}` доступны «Экономный», «Оптимальный»,
«Расширенный». Первый предпочитает меньший опубликованный тариф среди обязательных
ролей, второй — меньше неуточнённых технических условий, третий включает также
необязательные роли и предпочитает подробнее заполненные программу/портфолио.
Причины раскрыты в каждом варианте; это не рейтинг качества, оплаченный приоритет
или гарантия оптимума. Если предложение каталога ограничено, варианты могут совпасть.

Сервер учитывает роли/количество, город или явно заявленный выезд, вместимость,
полное окно календаря с известными буферами и совместимость с выбранными залами.
Известная несовместимость исключает пару; unknown остаётся явно указанным.
Для площадок нужен опубликованный, claimed профиль с календарём владельца.
Свои активные резервы учитываются только в авторизованном контексте этого события.
Отсутствующее окончание не заменяется выдуманным окном. Ориентиры берутся только
из опубликованных пакетов, не включают сервисный сбор и не становятся quote.
Стоимость нескольких залов одной площадки требует отдельного предложения:
сервер не умножает общий тариф и не считает его ценой всего набора.

Миграция `e6f7a8b9c0d1_event_plans` добавляет EventPlan с revision и JSON выбора
по requirement/position/artist или venue+hall. API:

- `GET /events/{id}/matching` — варианты, проверенный текущий выбор, кандидаты,
  неизвестные условия, незакрытые роли, серверные ориентиры и права пользователя.
- `PUT /events/{id}/plan` — writer-only сохранение с revision/context, проверкой
  актуальных ролей/календарей/совместимости и идемпотентным одинаковым повтором.
- `PATCH /events/{id}/planning-context` — writer-only окончание и объявленный
  бюджет; изменение окна запрещено после появления неотменённой сделки.

План не создаёт Request/Offer/Booking и не удерживает даты. Пользователь может
заменить каждую позицию, сохранить её и отдельно отправить заявки. Перед отправкой
UI перечитывает план/календари; несохранённый выбор блокирует кнопку. Повтор
использует EventCommandReceipt и существующие активные заявки, сохраняя отсутствие
дублей. Изменения плана не отменяют ранее отправленные заявки или сделки.
Viewer видит результат, но не может изменять. API защищены membership, writer RBAC,
rate limits, SMART_MATCHING; audit не копирует заметки/контакты/ключи.

Проверки:

- `cd apps/api && ../../.venv/bin/python -m pytest -q tests/test_matching.py`
  — **9 passed** (3.21s): три разных состава, отсутствие автоматических сделок,
  инвариант Premium, full-window/busy/buffer, технические несовпадения, IDOR/viewer,
  concurrent revision/context, stale calendar, client price injection, свои holds,
  неизменность существующего quote после изменения бюджета, multi-hall и synthetic.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api`
  — **306 passed, 2 skipped** (69.91s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/smart-matching.spec.ts e2e/event-command-retry.spec.ts e2e/compatibility.spec.ts --workers=1 --reporter=line`
  — **7 passed** (17.4s). E-CUST-01: Studio → API error/retry → три варианта →
  сохранение без запросов → ручная замена → серверный ориентир → ручная отправка
  и повтор без дублей. Desktop/390 без горизонтального переполнения; PR CI включает
  сценарий. Дополнительно сохраняются снимки вариантов и текущего выбора.

Это закрывает отдельный инкремент подбора. Compare V2, серверные EventReadiness/
next_best_action и budget-summary, collaboration/repeat/Business и прочие открытые
разделы master task продолжают работу. Поле matching.state=ready обозначает только
наличие окна/ролей для подбора, не готовность события к проведению.

Финальный повтор E-CUST-01 после настройки снимков обычного viewport:
`cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/smart-matching.spec.ts --workers=1 --reporter=line`
— **2 passed** (6.1s). Просмотрены три карточки на desktop и текущий выбор/вариант
на 390 px; закреплённая навигация остаётся в реальном интерфейсе.


## Budget Control

`GET /events/{id}/budget-summary` — новый read-only endpoint с membership,
per-user rate limit и приватным audit `event.budget_viewed`. Доступен также viewer;
не зависит от выключения рекламных/платёжных функций. Новая миграция не нужна:
используются Event.budget_rub, EventPlan, Request/OfferVersion/Booking/BookingHold.

Сервер возвращает declared_budget, confirmed_total, active_offers_total,
estimated_remaining, uncovered_requirements и state. Все суммы предложений —
сбор заказчика плюс гонорар из активного сохранённого quote; старые версии с
историческим total не пересчитываются сегодняшней fee policy. Отсутствующий или
нерублёвый снимок даёт неизвестный итог соответствующей группы и остаток, не ноль.

- Confirmed/InProgress/Completed и Dispute входят в confirmed_total; спор явно
  требует проверки взаиморасчёта. Это не утверждение об оплате или выплате.
- Живые DateHeld/AwaitingContract/AwaitingPayment входят в предложения.
  Подтверждённые сделки и удержания учитываются полностью, даже сверх количества
  ролей или без роли; UI показывает предупреждение, а не скрывает обязательства.
- Negotiation учитывается, когда выбран соответствующий участник EventPlan либо
  оставшиеся предложения однозначно помещаются в количество свободных позиций.
  Конкурирующие альтернативы без выбора показаны отдельно, не складываются.
- Отменённые/закрытые и просроченные удержания исключены. Read endpoint не запускает
  expiry worker и не притворяется, что статус уже изменён. Отмены/споры отдельно
  предупреждают: это не расчёт удержаний, возвратов или баланса платежей.
- Остаток равен бюджету минус подтверждённые и включённые предложения. Нулевой
  бюджет — реальный ноль; отсутствующий — unknown; отрицательный остаток — перерасход.
- Ориентиры оставшегося предварительного выбора показаны отдельно, без fee и без
  вычитания из остатка. Та же позиция не считается по тарифу и quote одновременно.
  Общий тариф площадки не умножается на несколько залов и не прибавляется к уже
  включённому офферу другого зала этой площадки.

На `/events/{id}` добавлена сводка с четырьмя суммами, состоянием расчёта,
незаполненными позициями, расшифровкой сделок/альтернатив и объяснением метода.
Есть loading/error/retry, read-only просмотр, ручное обновление. Сохранение состава,
окончания или бюджета обновляет сводку. Числа на клиенте только форматируются.
Мобильная версия использует одну колонку, desktop — четыре; реальные снимки 390
и 1440 px просмотрены. API определяет цену, UI не создаёт формул.

Проверки:

- `cd apps/api && ../../.venv/bin/python -m pytest -q tests/test_event_budget.py`
  — **9 passed** (3.37s) до последнего уточнения unknown; затем файл повторно
  включён в полный API-прогон. Сценарии: альтернативы/явный выбор, новая версия,
  историческая цена/нет quote, несколько позиций, избыточные подтверждённые сделки,
  live/expired hold, cancellation/dispute, нулевой/отсутствующий бюджет, multi-hall,
  membership/viewer/audit, реальный stub lifecycle с переходом суммы без удвоения.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-budget.spec.ts e2e/smart-matching.spec.ts e2e/booking-payment.spec.ts --workers=1 --reporter=line`
  — **7 passed** (17.0s). E-CUST-03 проходит API error/retry → два конкурирующих
  предложения → сохранённый выбор → budget deficit → контракт/stub capture →
  перенос суммы в confirmed без удвоения на 1440/390. Сценарий добавлен в PR CI.

Server EventReadiness/next_best_action ещё не реализован: прежний eventDayOps
ошибочно считает любой booking_id закрытием роли, включая Negotiation. Его нужно
заменить проверкой фактических сделок/ack/hold/совместимости/договора/оплаты.
Budget Control не является готовностью события или общей готовностью запуска.

Финальный повтор E-CUST-03 после обработки отсутствующего снимка цены и уточнения
текста метода: та же команда только с `e2e/event-budget.spec.ts` — **2 passed**
(9.6s). В полном API-прогоне также найден и устранён flaky assert старого
`test_hidden_venue_prices_are_not_exposed_even_to_its_owner`: строка `777` могла
случайно оказаться в UUID. Проверка теперь прямо проверяет отсутствие сумм и
источников тарифов, сохраняя проверку скрытого названия пакета.

Финальная приёмка текущего кода:
`PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **315 passed, 2 skipped**
(73.07s); повтор `make lint`, `make web-lint` и `make web-build` с указанными выше
локальными API URL — passed. Сводка бюджета принята отдельным инкрементом;
полный master task остаётся в работе.


## EventReadiness и следующий шаг заказчика

Добавлен derived server service `event_readiness.py`. Он использует факты Event,
сохранённого состава, quote/ack, Booking/BookingHold/slot, Contract, Payment и
Compatibility Engine. Новая DB-таблица/миграция не нужна: результат пересчитывается
при чтении, существующие сделки и их состояния не изменяются.

API:

- `GET /events/{id}/readiness` — score, checklist, blockers, next_best_action,
  required coverage, данные проверок выбранных участников и технические вопросы.
- `GET /orgs/{organization_id}/event-readiness` — ближайшие 12 незавершённых событий
  (включая Draft и последние сутки), по каждому свой прогресс/следующий шаг.

Оба endpoint проверяют membership до чтения, используют per-user rate limits и
приватный audit без контактов/цен/текстов переписки. Viewer может читать. Расчёт
не требует включённой оплаты и не создаёт дополнительный запрет на оформление.

Проверки охватывают окно, обязательные роли, выбор, получение предложения,
двусторонний ack, закрепление даты, договор, оплату, подтверждение сделки,
фактические календари и artist/hall compatibility. Уже закреплённые дополнительные
или избыточные сделки также требуют проверки; невыбранные конкурирующие предложения
не увеличивают число подготовленных ролей. Один истёкший резерв не заполняет
несколько позиций. Unknown не даёт баллов; без обязательных ролей score=0.
Score — доля выполненных проверок, не вероятность успешного события и не гарантия.

Доступность относится и к конкретному забронированному слоту: другой свободный
слот того же профиля не скрывает неправильное окно сделки. Истёкший hold не
считается активным даже до фоновой обработки. Просмотр не запускает expiry и не
меняет состояния. Спор, любое поступление денег без закреплённой даты (включая
частичную сумму) или противоречивый Confirmed/InProgress направляют в комнату
сделки к поддержке. Критическое внимание не скрывается при переходе события
в InProgress. Состояния Completed/Cancelled не получают фиктивный текущий процент.

Техническая проверка использует действительные выбранные залы. Unknown и
несоответствия остаются вопросами для согласования, даже после оплаты. Для
площадки вне каталога сводка не притворяется, что проверила её оснащение; без
фактов этот пункт не становится готовым. Ручная переписка сама по себе не меняет
технический статус и не создаёт AI-подтверждения совместимости.

На `/events/{id}` — progress/checklist, главный серверный следующий шаг,
раскрываемые причины и `Продолжить организацию`, loading/error/retry. В кабинете
заказчика новая сводка заменила прежнюю общую подсветку стадий разных событий.
Тестовые оплаты явно помечены «Деньги не списывались». Ссылка технического шага
передаёт event/artist/venue/hall, форма совместимости выбирает именно этот зал.

Исправлена старая ошибка eventDayOps: наличие booking_id больше не закрывает роль.
`GET /events/{id}` добавляет booking_status; только Confirmed/InProgress/Completed
считаются подтверждёнными. Старый счётчик общей готовности удалён, список заявок
сохранён как управление ролями/поиском/заменами. Убраны raw booking/offer коды
в тексте блокеров.

Для исторического Event с отсутствующим ends_at разрешено заполнить окончание
после появления сделок только в пределах всех их существующих слотов. Начало,
слоты, hold, quote и подписи не изменяются. Увеличение за пределы слота — 409;
после заполнения действует прежний запрет менять заданное окно при активной
сделке. Это позволяет уточнить отсутствующие данные без изменения договорных
снимков или выдумывания времени.

Проверки EventReadiness включают: полный реальный API lifecycle до двух stub
подтверждений, unknown после оплаты, полный/частичный late capture, expired hold
без мутации, один reserve на несколько позиций, неправильный booked window,
busy overlay, dispute/InProgress, отсутствие обязательных ролей/окна,
противоречивое подтверждение, membership/viewer/overview и дополнение отсутствующего
окончания без изменения quote. Полный состав команд/итогов приведён ниже.

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-readiness.spec.ts e2e/event-day-ops.spec.ts e2e/event-budget.spec.ts e2e/smart-matching.spec.ts e2e/compatibility.spec.ts --workers=1 --reporter=line`
  — **14 passed** (29.6s) до дополнения сценария для исторического окончания.
  E-CUST-05: ошибка/retry → Negotiation не закрывает роли → hold → contract/stub
  → 100% → кабинет → изменение техники → технический blocker → правильный зал
  в compatibility. Desktop/390 и скриншоты сводки/кабинета просмотрены; без overflow.
  В PR CI добавлены E-CUST-05 и исправленные eventDayOps проверки.

Compare V2, collaboration/repeat/Business, полное покрытие уведомлений/admin/SEO
и итоговый аудит остальных разделов master task остаются открытыми. Этот
инкремент не подтверждает общей готовности коммерческого запуска.

Финальная приёмка после обработки частичного поступления денег, противоречивого
Confirmed и заполнения отсутствующего окончания:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **326 passed,
  2 skipped** (74.80s). Файл test_event_readiness.py содержит 11 пройденных
  сценариев с учётом параметризации.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-readiness.spec.ts e2e/event-command-retry.spec.ts --workers=1 --reporter=line`
  — **5 passed** (15.8s). E-CUST-05 теперь начинает с события без ends_at при
  существующих предложениях, заполняет допустимое окончание через UI и завершает
  весь дальнейший путь. Повтор создания/отправки заявок также не сломан.


## Compare V2 — инкремент 2026-09-12

`GET /compare` сохраняет порядок выбранных 2–4 профилей; сервер возвращает
публичные факты и опубликованные пакеты без расчёта договорной цены. Подписки
не влияют на порядок, Verified, completed deals, response time или отзывы.
Артисты: окно календаря с известными setup/teardown, формат, состав, программа,
длительность, выезды, техника/райдер, наличие портфолио, тарифы, measured response
и отзывы конкретного профиля. Средняя оценка — от пяти Completed-отзывов;
тексты/author IDs в Compare не возвращаются. Unknown явно отделён от соответствия.

Площадки: район/метро, вместимость каждого зала, пакеты, фактические окна,
оборудование и ограничения владельца. Не складываются вместимости/тарифы залов.
Синтетический календарь не выдаётся за owner availability/подтверждённую технику.
Непубличный профиль не раскрывается даже по известному ID. При выборе пары
artist + venue + hall вызывается существующий Compatibility Engine, включая
полное окно/буферы и список вопросов, которые требуется согласовать.

Авторизованный пользователь выбирает своё событие и позицию роли. Время/город/
гости берутся из Event; public query не может подменить их. Свои holds учитываются
только после object authorization. «Добавить в событие» сохраняет EventPlan через
его существующую команду: роль/позиция, конкретный зал, writer RBAC, context token,
revision, идемпотентный повтор и повторная проверка доступности/совместимости.
Заявки, офферы, holds и платежи при этом не создаются. Конфликт версии требует
обновить сравнение и явно выбрать замену; чужие изменения не перезаписываются.

В профилях обеих сторон есть единая кнопка «Сравнить» и локальная подборка до
четырёх участников. Из `/compare` можно удалить профиль или сбросить подборку;
есть empty/loading/error/retry, readonly-состояние, ссылки входа/создания события.
Дата без окончания даёт подсказку, а не ошибку обычного ввода. Страница noindex.
Факты площадки теперь учитывают завершённые сделки и первые предложения по
заявкам её залов; не смешивают разные площадки одной организации.

Проверено локально на изолированной SQLite и production-сборке Next:

- `cd apps/api && ../../.venv/bin/python -m pytest -q` — **333 passed, 2 skipped**
  (76.38s). В `test_comparison.py` 7 новых сценариев: факты/порядок после Premium,
  полное окно и буферы, hall/synthetic/hidden, event IDOR и свои holds, hall metrics,
  UUID/дубликаты/отсутствие автоматических команд, Completed threshold/приватность.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/compare-v2.spec.ts e2e/smart-matching.spec.ts e2e/artist-presentation.spec.ts e2e/compatibility.spec.ts --workers=1 --reporter=line`
  — **9 passed** (34.4s). E-CUST-02 desktop/390: 503/retry, фактические цены и
  райдер, конфликт revision после изменения в другой вкладке, явное обновление
  и замена, добавление конкретного зала, ноль автоматических заявок, удаление
  подборки. Регрессия EPK/подбора/совместимости пройдена. Скриншоты desktop/390
  просмотрены после уплотнения отступов; layout overflow отсутствует.

Новых таблиц и миграций этот инкремент не требует. E-CUST-02 добавлен в PR CI;
удалён дублирующий старый `/compare` handler из shortlists router. Collaboration,
repeat/Business, оставшиеся уведомления/admin/SEO, PostgreSQL runtime acceptance,
provider handoff и полный аудит остальных пунктов master task остаются открытыми.

## Совместные подборки — инкремент 2026-09-14

Создание в избранном: явный выбор 2–4 кандидатов одного типа, название, срок и
необязательная связь с событием той же организации. От события доступен переход
к созданию, список связанных подборок и результаты. Writer RBAC нужен для
создания/отзыва; viewer видит результаты без capability-ссылки. Текущая membership
проверяется при каждой команде. Повтор создания с тем же Idempotency-Key сохраняет
одну подборку; изменённое тело с прежним ключом отклоняется.

`SharedShortlist` дополнен event_id/collaborative. Новые `ShortlistGuest` и
`ShortlistFeedback` хранят хеш гостевого ключа, публичное имя, одну текущую реакцию
и редактируемый комментарий на кандидата, revision. Гость без аккаунта может
голосовать, отметить «нравится»/«не подходит», изменить мнение, удалить свой
комментарий. Повтор не увеличивает счётчики; stale revision отклоняется.
Сериализация команд на строке подборки защищает join/update/revoke от гонок.

Каждое гостевое чтение/изменение проверяет срок и отзыв share token; запись также
требует collaborative mode и отдельную capability из X-Shortlist-Guest. Она не
принимается как сессия аккаунта и не действует на другой shortlist или кандидата.
Публичный payload не содержит Event ID, орг ID, бюджета, документов, owner ID,
аккаунтных/гостевых токенов и контактов. Профиль площадки, снятый с публикации,
больше не раскрывается через сохранённый snapshot. Ввод имён/комментариев ограничен;
телефоны/email/внешние ссылки не принимаются в обсуждение. HTML отображается текстом.
Ответы и fetch — no-store, referrer policy no-referrer. Account Authorization и
активная организация не передаются guestApi.

Rate limits применяются до поиска share, с ключом прямого peer без доверия к
произвольному X-Real-IP. Лимиты хранения: до 20 активных подборок организации,
50 гостевых устройств на подборку, 1000 символов комментария. Список показывает
до 100 подборок с приоритетом неотозванных/позднего срока; активные попадают в лимит.
Гостевые имена не верифицированы; счётчики не подтверждают уникальных людей и не
влияют на публичные отзывы/Verified/рейтинг. Никаких автоматических заявок, брони
или изменения EventPlan. Копирование ссылки — ручное действие, отправок нет.

`BOOKER_COLLABORATIVE_EVENTS=false` выключает создание совместных ссылок, join и
feedback; сохраняет чтение результатов и отзыв. Старые ссылки имеют
collaborative=false независимо от глобального флага и остаются read-only.

API:

- `POST /shortlists`: расширен TTL/явным collaborative/event_id/idempotency.
- `GET /shortlists?organization_id=&event_id=`: авторизованные результаты и права.
- `POST /shortlists/{id}/revoke`: отзыв по writer RBAC с текущей membership.
- `GET /shared/{token}`: доступные публичные кандидаты, мнения и собственная revision.
- `POST /shared/{token}/guests`: идемпотентное вступление с отдельным ключом устройства.
- `PUT /shared/{token}/items/{target_id}/feedback`: замена/снятие реакции и комментария.

Миграция `f7a8b9c0d1e2_shortlist_collaboration`, после `e6f7a8b9c0d1`. Проверен
upgrade с legacy-ссылкой и snapshot, downgrade/upgrade: token/данные сохранены,
новые ссылки не открывают совместный режим старым. Это SQLite migration acceptance;
PostgreSQL runtime acceptance остаётся отдельным общим пунктом.

Приёмка этого инкремента:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **342 passed,
  2 skipped** (67.81s). Восемь collaboration tests + отдельный migration roundtrip:
  реакции/комментарий/удаление/replay, scope/IDOR, приватность/audit/cache,
  expiry/revoke, create idempotency и viewer, legacy/validation/rate, скрытая
  площадка, global flag. Старые shortlist/compare tests также проходят.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed после сборки.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/collaboration.spec.ts e2e/compare-v2.spec.ts e2e/event-readiness.spec.ts --workers=1 --reporter=line`
  — **6 passed** (29.0s), desktop/390. E-COLLAB-01: переход от события в избранное,
  потеря ответа после успешного создания и повтор без дубля, отдельный browser
  context гостя без аккаунта, 503/retry, три реакции, комментарий, сохранение после
  reload, результаты организатора, отзыв и отклонение изменения в уже открытой
  гостевой вкладке. Event.requests остаётся пустым. Скриншоты гостя/организатора
  просмотрены, горизонтального overflow нет. Сценарий включён в PR CI.

Лимитер остаётся существующим in-process механизмом; проверка production proxy и
масштабирования входит в оставшийся общий security/performance audit. Повтор
событий, Business, оставшиеся уведомления/admin/SEO, полная PostgreSQL-проверка и
provider handoff/master acceptance ещё не завершены. Этот коммит не означает
общей готовности коммерческого запуска и не меняет внешние production-гейты.

## Повтор завершённого события — инкремент 2026-09-14

`GET /events/{id}/repeat-options` возвращает авторизованный preview Completed:
формат, город, гостей, роли и участников только фактически Completed bookings.
`POST /events/{id}/repeat` требует writer RBAC, Completed, явные новые будущие
начало/окончание, название и Idempotency-Key; выбранные preferred_request_ids
должны принадлежать Completed-сделкам исходного события. Новое тело со старым
ключом отклоняется; replay проверяет текущую membership до чтения результата.

Создаётся отдельный Draft в той же организации. Роли получают новые ID, открытые
статусы и прежние category/qty/required/порядок. Формат, город и число гостей
сохраняются; бюджет и свободные заметки не переносятся. Нет копирования Request,
Offer/OfferVersion/quote_id, Booking/Hold, Payment, Contract, подписей, календарных
слотов и состояния подтверждённой доступности. Исходный Event не изменяется.

Необязательные предпочтения сохраняются в отдельном `EventRepeatPreference`
(миграция `b9c0d1e2f3a4`, после `f7a8b9c0d1e2`), без создания EventPlan.
`GET /events/{id}/repeat-preferences` заново сопоставляет их с текущим календарём,
ролями, городом, вместимостью и выбранными залами через MatchingContext.
Неизвестные условия по-прежнему требуют согласования; проверка не является
обещанием доступности. Недоступные профили/неуказанные позиции нельзя автоматически
включить. После явного «Включить в состав» используется существующий PUT plan с
повторной проверкой, context/revision и writer RBAC. Заявка при этом не создаётся.

Completed-событие показывает форму повтора; новый Draft — отдельный список
предпочтений с перепроверкой и явным добавлением. Предварительный состав обновляется
после добавления. Есть loading/error/retry, readonly и feature-off состояния.
`BOOKER_REPEAT_EVENTS=false` закрывает создание повторов и добавление предпочтений,
оставляя чтение авторизованной истории. Новых provider inputs нет.

Связанная защита жизненного цикла: обычная заявка, quick-request в существующее
событие и новый первичный оффер не могут снова перевести Completed/Cancelled в
RequestSent/Negotiation. Статус читается после блокировки строки Event. Replay уже
сохранённой заявки остаётся чтением прежнего результата, без повторной мутации.

Проверки повтора:

- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **348 passed,
  2 skipped** (76.79s). Шесть новых тестов: clean Draft/roles/preference + новая
  доступность, optional/replay/body conflict, Completed/date/RBAC, Completed-only
  candidates/flag/current membership, migration upgrade/downgrade/upgrade,
  запрет reopen через request/quick-request/offer.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-repeat.spec.ts e2e/event-command-retry.spec.ts e2e/smart-matching.spec.ts --workers=1 --reporter=line`
  — **7 passed** (20.0s). E-REPEAT-01 desktop/390 создаёт реальную изолированную
  тестовую цепочку offer → ack → hold → contract/OTP → stub payment → check-in/out
  до Completed; затем через UI создаёт повтор с потерей ответа/retry без дубля.
  Новый Draft без заявок/бюджета, старое событие Completed; участник недоступен до
  открытия нового окна, после перепроверки явно добавляется в EventPlan, форма
  состава сразу обновляется. Заявки не создаются. Скриншоты desktop/390 просмотрены,
  overflow отсутствует. E-REPEAT-01 добавлен в PR CI.

Проверки миграции выполнены на SQLite; PostgreSQL runtime остаётся в общей
приёмке. Остальные разделы master task, включая Replacement UX/Business и
оставшиеся security/operations/provider задачи, продолжаются.

После уточнения подписи предпочтений повторены production build и E-REPEAT-01:
`npx playwright test e2e/event-repeat.spec.ts --workers=1 --reporter=line` с теми же
API/WEB env — **2 passed** (6.9s); `make web-lint` также passed.

## Replacement UX — 2026-09-14

Расширен существующий `GET /events/{id}/requirements/{requirement_id}/replacement`: полное окно события по Москве, доступные кандидаты, причины/неизвестные условия, право отправки, состояния без окна/без вариантов/закрытого события. Каталог на один день больше не выдаётся за проверенную замену.

Проверяются город/выезд, роль, вместимость, опубликованный заявленный владельцем зал, календарь на всё окно и известные buffers, техническая совместимость с подтверждённым/удержанным и предварительным составом. Известная несовместимость исключает вариант; неизвестные условия показаны отдельно. Предыдущие заявки и уже используемые ресурсы не предлагаются повторно. Несколько залов допускают размещение артиста в подходящем зале.

`POST /events/{id}/requirements/{requirement_id}/replacement-requests` доступен только writer своей организации, повторно проверяет подбор под блокировкой события и создаёт обычную Request с durable idempotency receipt. Не создаёт OfferVersion, hold, оплату или договор. Повтор после потерянного ответа возвращает ту же заявку; изменённое тело/устаревший кандидат дают конфликт. Есть rate limits и audit. Новая миграция не требуется.

Статус Booking имеет приоритет над старым статусом Request при расчёте закрытых позиций. Запросы и новые предложения больше не переводят начавшееся событие обратно из InProgress в RequestSent/Negotiation.

UI в событии: «Подобрать замену», полное окно, свободные варианты, причины и раскрываемые условия, явный запрос нового предложения, loading/error/retry/empty, права viewer. Без гарантии замены. E-REPLACE-01 добавлен в PR CI; desktop/390 проверяют занятое и короткое окно, изменение календаря после открытия, пустое состояние и потерю ответа после отправки без дубликата. Скриншоты просмотрены, горизонтального overflow нет.

Проверено для replacement:
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **353 passed, 2 skipped** (70.72s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/event-replacement.spec.ts e2e/event-day-ops.spec.ts e2e/event-repeat.spec.ts e2e/event-command-retry.spec.ts --workers=1 --reporter=line` — **14 passed** (16.9s).

Полный master task остаётся активным: Business, notifications, admin commercial,
SEO, security/performance/operations, provider handoff и итоговая приёмка продолжаются.

## Business: templates, clean drafts, private notes — 2026-09-14

Добавлены рабочие шаблоны и копирование событий в `/cabinet/customer/business`,
внутренние заметки — в карточке события. Это часть раздела 20, а не завершение
всего Business: управление командой/лимиты мест, история поставщиков,
аналитика/экспорты и приоритетная поддержка ещё проверяются и дорабатываются.

- Шаблон сохраняет неизменяемый снимок города, формата, числа гостей, планового
  бюджета и ролей события своей организации. До 100 активных шаблонов, архив
  без изменения уже созданных событий. Изменения исходного события не меняют шаблон.
- Создание из шаблона или копии текущего события требует нового названия и будущего
  окна с часовым поясом; UI использует Москву. Новый Event — Draft с новыми ID ролей.
  Старые даты, сделки, предложения, quote_id, брони, оплаты, подписи, участники,
  EventPlan и внутренние заметки не переносятся. Сумма переносится только как
  объявленный бюджет, не договорная цена. Повтор завершённого состава остаётся
  отдельной доступной ранее функцией, с новыми проверками дат.
- `customer.templates` и `customer.notes` проверяются сервером через действующий
  тариф/feature flag; writer своей customer-организации. Сохранённые шаблоны и
  заметки читаются участниками после истечения тарифа, новые платные действия
  заблокированы. Архивирование шаблона и удаление заметки остаются доступны по RBAC.
- Заметки видны только организации заказчика. Автор может редактировать свои
  заметки; владелец/администратор может удалить чужую. Viewer только читает.
  Редактирование/удаление проверяет revision; удаление очищает текст. До 4000
  символов, пагинация по 50, имя автора и дата в UI. Тексты не попадают в audit.
- Создание шаблона, черновика и заметки — durable idempotency receipts, блокировки,
  rate limits, audit. Replay после исключения пользователя из команды запрещён.
  Изменённое тело с прежним ключом — конфликт. Отдельные состояния загрузки,
  ошибок/повтора, пустого списка, отсутствия тарифа и прав.

Миграция `c0d1e2f3a4b5_business_workflows.py` после `b9c0d1e2f3a4`:
`business_event_templates`, `business_event_notes`. Проверен SQLite upgrade на
новой базе, downgrade к предыдущей версии и повторный upgrade, включая FK.
Локальная E2E-база исторически создана `init_schema`, без Alembic ledger: попытка
полного upgrade выявила существующие таблицы; новые таблицы для браузерного
прогона созданы штатным test `init_schema`. Это не подменяет отдельный пройденный
миграционный тест. PostgreSQL runtime остаётся в общей приёмке.

API:
- `GET/POST /business/organizations/{org_id}/templates` — свои шаблоны / снимок своего события.
- `POST /business/templates/{id}/archive` — архив.
- `POST /business/templates/{id}/events` — чистый Draft из снимка.
- `POST /business/events/{id}/clone` — чистый Draft из текущего брифа.
- `GET/POST /business/events/{id}/notes` — список / внутренняя заметка.
- `PUT/DELETE /business/notes/{id}` — редактирование автора / удаление по правам с revision.

Проверки этого этапа:
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` — **359 passed, 2 skipped** (84.57s).
- После усиления данных исходного события реальным предложением и проверки replay
  после удаления из команды: `.venv/bin/python -m pytest apps/api/tests/test_business_workflows.py -q`
  — **6 passed** (3.99s), включая миграцию.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/business-workflows.spec.ts e2e/commercial.spec.ts e2e/event-repeat.spec.ts --workers=1 --reporter=line`
  — **11 passed** (23.8s). Desktop/390: Standard без платных действий → явная stub
  активация Business → заметка с потерей ответа/retry → редактирование → шаблон →
  чистый Draft с потерей ответа/retry → удаление заметки → прямая копия → архив
  шаблона. Проверены отсутствие дублей и переноса заметок, бюджет/роли, overflow.
  Скриншоты шаблона, заметок и мобильной формы просмотрены. Сценарий добавлен в PR CI.

## Team management and plan seats — 2026-09-14

Добавлены `/team` и `/team/join`, переходы из профиля и коммерческого кабинета.
Коммерческий кабинет передаёт выбранную организацию явно. В команде видны имена,
роли, право подтверждения предложений, число участников/приглашений и лимит тарифа.
Владелец/администратор приглашает, отзывает приглашение, изменяет права и удаляет
участника. Назначать владельцев/администраторов и управлять ими может только
владелец (или platform admin). Последнего владельца нельзя удалить/понизить.
Viewer не получает controls управления или адреса приглашённых.

Места разрешаются серверным entitlement `team.seats`: Standard/Free 1, Pro 2,
Premium/Business 5 по текущему catalog. Считаются участники и неистёкшие,
неотозванные, непринятые приглашения. Операции сериализуются блокировкой организации.
Старый `POST /orgs/{id}/members` использует тот же лимит и audit, обхода через него
нет. В тестах существующих RBAC-сценариев явно задаётся подходящий платный тариф
через `grant_team_plan`; отдельные тесты лимитов проверяют настоящие Free/Pro/
Premium/Business без такого обхода проверки. При downgrade/expiry существующие
участники не теряют доступ и не удаляются; новые места требуют свободной ёмкости.
Выключение customer_business блокирует новые Business-места.

Приглашение привязано к организации и email аккаунта, срок 7 дней. 256-битный
секрет создаётся браузерным crypto; сервер хранит только SHA-256. Ссылка передаётся
пользователем вручную, транспортных отправок нет. Секрет находится во fragment,
после открытия переносится в sessionStorage и удаляется из адресной строки;
preview/accept передают его в заголовке только после входа. Страница join noindex /
no-referrer. Перед принятием пользователь видит организацию и предоставляемую роль.
На accept заново проверяются адрес аккаунта, срок/отзыв, действующие полномочия
пригласившего и текущие места тарифа. Повтор после потери ответа не создаёт второго
участника. Удалённый участник не возвращается по использованному приглашению.
Редактирование прав проверяет ожидаемые текущие значения. Серверные rate limits,
object auth, audit; секрет не возвращается в списке/аудите.

Миграция `d1e2f3a4b5c6_team_invitations.py` после `c0d1e2f3a4b5` создаёт
`team_invitations`; SQLite upgrade/downgrade/re-upgrade проверены отдельным тестом.
PostgreSQL runtime остаётся частью общей приёмки.

API:
- `GET /orgs/{id}/team` — команда, ёмкость, разрешённые действия и активные приглашения для управляющих.
- `POST /orgs/{id}/team/invitations` — приглашение с безопасным повтором по секрету.
- `POST /orgs/{id}/team/invitations/{id}/revoke` — отзыв.
- `POST /team-invitations/preview`, `/team-invitations/accept` — просмотр/принятие адресатом после входа.
- `PUT/DELETE /orgs/{id}/team/members/{id}` — права/удаление с object auth и last-owner guard.

Остальная часть Business (история поставщиков, аналитика и экспорты, приоритетная
поддержка), уведомления, admin commercial, SEO/security/operations/provider handoff
и итоговая приёмка master task продолжаются. Коммерческий запуск ещё не заявлен.

Проверки команды:
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `.venv/bin/python -m pytest apps/api/tests/test_team.py -q` — **7 passed** (1.74s):
  Free/direct endpoint limits, Pro/Premium seats, pending reservations, downgrade,
  flag, expiry/revocation, account binding, safe retries, member removal, admin/owner
  authority, last-owner guard, current inviter permissions, platform support and migration.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/team.spec.ts e2e/business-workflows.spec.ts e2e/commercial.spec.ts --workers=1 --reporter=line`
  — **11 passed** (22.9s). После добавления отдельного снимка join-экрана тот же
  `e2e/team.spec.ts` — **2 passed** (4.6s). Team/Join desktop/390 просмотрены,
  overflow отсутствует; секрет приглашения маскируется на снимке команды.
  Сценарий входит в PR CI.
- Финальный `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` —
  **366 passed, 2 skipped** (71.76s), включая все новые сценарии команды.

### Business: аналитика, история поставщиков и экспорт документов

Реализованы `GET /business/organizations/{id}/report` и
`GET /business/organizations/{id}/documents.zip`, подключённые к Business-кабинету.
Доступ проверяет членство организации и отдельные entitlement analytics/history/exports.
Период — даты событий по Москве, максимум два года и 1000 событий для отчёта,
100 событий/20 МБ для ZIP. UI показывает выбранный период, пустое состояние,
ошибку, обновление и страницы по 25 событий/поставщиков.

Подтверждённые условия берутся из активных immutable OfferVersion; неизвестная
или нерублёвая сумма не превращается в ноль. Записи успешных нетестовых оплат,
тестовые оплаты и ожидаемые оплаты разделены. Это отчёт по событиям, не бухгалтерский
баланс и не остаток после возвратов. История объединяет обращения к артисту или
площадке/залу и содержит ссылки на соответствующие события организации.

ZIP содержит сохранённые тексты договоров со статусами подписания, все версии
условий, сводку событий и manifest. HTML экранируется; коды подписания, переписка,
вложения и внутренние заметки исключены. Новых договоров/подписей экспорт не создаёт.
Новой миграции нет. Изоляция чужих документов и профилей проверена API-тестами.

Проверки: `make lint`, `make web-lint`, `make web-build` — passed;
`.venv/bin/pytest apps/api/tests/test_business_reporting.py -q` — 4 passed.
`cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/business-workflows.spec.ts --workers=1 --reporter=line`
— 2 passed (25.7s), desktop/390: выгрузка ZIP, смена периода, пустое состояние,
отсутствие overflow. Оба снимка просмотрены. Сценарий уже включён в PR CI.

Следующий блок — приоритетная поддержка; уведомления, коммерческая админка,
SEO/security/operations/provider handoff и итоговая приёмка всей цели остаются в работе.
Полный `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make test-api` после изменений:
**370 passed, 2 skipped** (87.16s).

### Поддержка: приоритетная очередь и безопасная отправка

Расширены существующие `/support/tickets` POST/GET и `/{id}/close`, добавлен
`GET /support/tickets/{id}` для защищённого чтения текста. Сервер сохраняет
`support.priority` при создании; downgrade/expiry не переписывает принятую
очередь. Обычные пользователи видят только собственные обращения, оператор
платформы — очередь с фильтром состояния, страницами до 100 и FIFO внутри
приоритетных/обычных открытых обращений. Административный доступ использует
существующую проверку TOTP-сессии при включённом enforcement.

`Idempotency-Key` связывается с автором и fingerprint содержимого/организации;
изменённое содержимое даёт 409. UI сохраняет ключ для повтора после потери ответа.
Старые клиенты без заголовка совместимы. Закрытие идемпотентно с единственной
записью аудита перехода. Тексты обращений не попадают в audit payload.

Миграция `e2f3a4b5c6d7_support_priority.py`: priority snapshot и ключ/fingerprint
отправки; существующие данные сохраняются с обычным приоритетом. SQLite
upgrade/downgrade/upgrade проверены на сохранённом старом обращении.
PostgreSQL runtime-проверка остаётся частью общей приёмки.

`/support`: русские категории/статусы, loading/error/empty, чтение текста,
закрытие, фильтры, страницы и выбор организации через профиль. `/admin`
содержит переход к очереди. Срок ответа не выдумывается. Следующее улучшение
для полной операционной готовности — переписка автора с оператором в обращении
и доставка уведомлений; текущая очередь обеспечивает чтение/закрытие.

Проверки:
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api` — **375 passed, 2 skipped** (147.15s).
  Первый прогон без изоляции: 374 passed, 2 skipped, 1 setup error (`database is locked`)
  при одновременной подготовке E2E-базы; повтор изолировал startup-базу в памяти.
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/support-priority.spec.ts --workers=1 --reporter=line`
  — **4 passed** (11.6s): Free/Business, потерянный ответ, чтение/закрытие автора
  и оператора, desktop/390. Все четыре снимка просмотрены, overflow отсутствует.
  Новая E2E-база создана полным Alembic upgrade head. Сценарий включён в PR CI.

Общая цель остаётся активной: ответы поддержки/уведомления, коммерческая админка,
SEO/security/operations/provider handoff и полная приёмка ещё не завершены.

### Поддержка: ответы автора и оператора

Добавлена приватная переписка внутри существующего обращения:
`GET/POST /support/tickets/{id}/messages`. Сообщение сохраняет автора и его роль
в момент отправки; доступ проверяется заново при каждом чтении/повторе. Только
автор обращения или platform operator с действующей TOTP-сессией (при enforcement).
Тариф не ограничивает ответы. Текст до 8000 символов; только непустой текст.
Объекты сделки, решения по спорам и платежи переписка не меняет.

POST требует `Idempotency-Key`, связанный с ticket/author; изменённый текст — 409.
Блокировка обращения сериализует отправку и закрытие. Закрытое обращение сохраняет
историю, запрещает новые ответы, но допускает получение результата уже принятого
повтора. В журнале только ID и роль, без текста сообщений.
GET возвращает до 100 сообщений, UI показывает страницы по 50 с переходами
к ранним/новым ответам, обновлением, loading/error/empty и повтором отправки.

Миграция `f3a4b5c6d7e8_support_replies.py` после `e2f3a4b5c6d7` создаёт
support_replies; применяется штатным Alembic upgrade. Проверен полный SQLite
цикл миграций в support-тесте и upgrade существующей E2E-базы. PostgreSQL
runtime остаётся в общей приёмке. Уведомления о новых ответах входят в следующий
блок общего notification coverage; отправок во внешние transports в этом блоке нет.

Проверки:
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- `BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/pytest apps/api/tests/test_support_priority.py -q` — **6 passed** (2.70s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api` — **376 passed, 2 skipped** (153.31s).
- `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/support-priority.spec.ts --workers=1 --reporter=line`
  — **4 passed** (20.7s). Оператор и автор работают в отдельных browser contexts;
  проверены потеря ответа/повтор, обмен сообщениями, закрытие и сохранённая история.
  Desktop/390 снимки переписки просмотрены, горизонтального overflow нет. Сценарий
  уже включён в PR CI. Цель master task ещё не завершена.

### Уведомления: постоянная адресная лента

Добавлена InboxNotification: получатель, dedupe key, шаблон/текст, объект, безопасная
внутренняя ссылка, created_at/read_at. Существующий `notify` сохраняет in-app запись
в транзакции исходного действия; внешний provider не требуется. Отключённый
in_app provider не создаёт новых записей. Старый audit transport сохранён для
совместимости, но интерфейс больше не использует глобальную выборку журнала.

`GET /notifications` сначала ограничивает данные получателем, затем применяет
фильтр непрочитанных/offset/limit (до 100), возвращает total и unread_count.
`POST /notifications/{id}/read` — только получатель, идемпотентно, с audit первого
изменения. Администратор не получает чужую ленту. URL ограничены внутренними
путями, переход к самой сделке/событию сохраняет проверки доступа целевого API.

Миграция `a4b5c6d7e8f9_notification_inbox.py` после f3a4b5c6d7e8 переносит валидные
старые in-app уведомления из audit, удаляет семантические дубли и пропускает
несуществующих получателей. Старые сообщения password reset переносятся с
безопасным текстом без токена. Новые запросы восстановления также не кладут
демо-токен в in-app ленту; ссылка восстановления относится к email transport.
Старые audit-записи не переписываются.

`/notifications` (noindex) содержит страницы по 25, непрочитанные, отметку прочтения,
loading/error/retry/empty и переход к объекту. SiteChrome показывает реальное число
непрочитанных, последние пять и ссылку на весь список; обновляет при навигации,
возврате фокуса, чтении и раз в минуту. В мобильной навигации есть «Входящие».
Ответы оператора идут автору обращения, уточнения автора — platform operators;
уведомление содержит только ссылку/номер, без текста приватного ответа.

Это фундамент раздела 21. Осталось добавить недостающие expiration/payment/blocker/
replacement notifications, проверить полное покрытие и consent, перевести SMTP
на доставку из committed outbox и завершить операционную приёмку. Коммерческая
админка, SEO/security/provider handoff и общая цель также остаются в работе.

API-проверки:
- `BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/pytest apps/api/tests/test_inbox.py apps/api/tests/test_notifications.py apps/api/tests/test_support_priority.py -q`
  — **17 passed** (3.46s): 105 чужих уведомлений не вытесняют своё, read IDOR,
  rollback/dedupe, безопасные ссылки, password-reset privacy, legacy migration.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api`
  — **380 passed, 2 skipped** (126.74s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint web-lint` — passed.
- До визуальной правки флажка: `cd apps/web && PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test e2e/support-priority.spec.ts e2e/commercial.spec.ts --workers=1 --reporter=line`
  — **11 passed** (27.7s). Support E2E расширен входящими: адресность, отсутствие
  приватного текста, ссылка, чтение, счётчик и пустой unread-фильтр. Уже входит в CI.
- Финальная сборка после визуальной правки: `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.
- Повтор `e2e/support-priority.spec.ts` с теми же переменными — **4 passed** (13.0s).
  Тест учитывает пагинацию накопленной очереди; закрытую историю проверяет автор.
  Финальные desktop/390 снимки входящих просмотрены, флажок и подпись выровнены,
  overflow отсутствует. Финальный `make web-lint` — passed.

### Email outbox: отправка после commit

SMTP transport теперь только создаёт запись EmailOutbox в исходной транзакции.
Worker обрабатывает её в отдельной сессии после commit: атомарный claim, deadline,
ограниченные повторы/backoff, максимум пять попыток, стабильный Message-ID.
Неоднозначный исход после начала SMTP-отправки и истёкший claim переводятся в
`uncertain` без автоматического повторного письма. Выключенный SMTP/отсутствующий
host не запускает доставку. Дедупликация сохраняет совместимость со старым ключом,
а новый reset token больше не подавляется ключом предыдущего письма пользователю.

Миграция `b5c6d7e8f9a0_outbox_claims.py` сохраняет существующие строки и добавляет
claim_token/claim_expires_at/next_attempt_at. Новый модуль
`python -m booker_api.notifications.worker` по умолчанию показывает только counts;
`--deliver --limit 1..100` включает ограниченную обработку. Подготовка и семантика
описаны в `docs/ops/EMAIL_OUTBOX.md`. Production расписание/SMTP не включались.

Проверки выделенного блока:
`BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/pytest apps/api/tests/test_outbox_delivery.py apps/api/tests/test_trust_outbox.py apps/api/tests/test_notifications.py -q`
— **17 passed** (2.98s). Файловая SQLite с отдельными соединениями подтверждает
невидимость незакоммиченного письма и rollback; тест второго worker проверяет
сохранённый claim; проверены disabled, retry/backoff/max attempts, ambiguous/crash,
legacy idempotency, новый reset и сохранение данных в migration upgrade/down/up.
SMTP подменён тестовым транспортом, реальных сетевых отправок нет.

На мигрированной локальной E2E-базе команда просмотра вернула
`state=inspection, counts={}`; вызов `--deliver --limit 1` с
`BOOKER_EMAIL_PROVIDER=disabled` вернул `state=disabled`, все счётчики 0.
Интерфейс здесь не менялся. Ручное разрешение uncertain/exhausted очереди остаётся
в admin/operations блоке. Полное notification coverage и вся master goal ещё в работе.
Финальный `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api`
— **387 passed, 2 skipped** (132.61s). `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint`
— passed. Web-код не изменялся; предыдущие web-build/web-lint/E2E результаты
относятся к той же версии интерфейса, новые браузерные проверки не заявляются.

### Уведомления о сроках и следующих действиях

Подключены in-app lifecycle hooks для окончания периода подписки и продвижения,
истечения hold, отмены сделки, проверки замены и перехода к оплате после двух
подписей договора. Доставка в той же транзакции, адресная, с semantic dedupe;
тексты не выдумывают оплату, свободную дату или гарантированную замену.
Новый действующий hold не освобождается из-за просроченного старого hold;
отмена DateHeld при expiry использует условный UPDATE и не перезаписывает
другой уже изменившийся статус сделки.

`python -m booker_api.notifications.maintenance` — просмотр очереди сроков,
`--run --limit 1..100` — ограниченная транзакционная обработка трёх типов объектов.
Руководство: `docs/ops/NOTIFICATION_MAINTENANCE.md`. Новых миграций нет.
Локальная inspection-команда вернула нулевые очереди, без изменения данных.
Email/SMS/push не вызываются этим обработчиком.

CommerceCabinet принимает `?organization=...`, реагирует на изменение query
и не выбирает другое пространство при отсутствующем доступе. Ссылки уведомлений
подписки/продвижения содержат нужную организацию. Уведомление замены ведёт
к ролям соответствующего события.

Проверки:
- `BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/pytest apps/api/tests/test_lifecycle_notifications.py apps/api/tests/test_event_readiness.py apps/api/tests/test_paid_promotion.py -q`
  — **24 passed** (13.02s): bounded expiry, recipient/period dedupe, новый hold,
  оплата ещё не создана, отмена/замена и существующие readiness/promotion сценарии.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api`
  — **390 passed, 2 skipped** (117.10s).
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint web-lint` — passed.
- `PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build` — passed.

Остаются event blocker notifications, реальный deadline предложений, operator
resolution email-очереди, остальные admin/SEO/security/provider handoff задачи
и полная приёмка master task. Цель не объявлена завершённой.

Браузерная проверка lifecycle: `npx playwright test e2e/commercial.spec.ts e2e/event-replacement.spec.ts --workers=1 --reporter=line` — 10 passed (15.3s), production build, desktop и 390px. Проверены переход из уведомления к замене и выбор организации по ссылке без подмены чужим кабинетом. Скриншоты обеих ширин просмотрены. Повторные `make web-build` и `make web-lint` прошли.

### Подготовка предложения из входящей заявки

`GET /requests` больше не подставляет 100 000 / 220 000 ₽ при отсутствии тарифа:
возвращает `honorarium_rub: null`. При нескольких тарифах ориентир — минимальный
фактический тариф; он не становится договорной суммой до явной отправки.
В кабинетах исполнителя/площадки используется форма проверки и ввода гонорара.
Комиссии и immutable quote по-прежнему формирует сервер.

Предлагаемый `slot_id` покрывает всё будущее окно события, учитывает монтаж и
демонтаж артиста, календарные буферы и busy/held/confirmed пересечения. Запрос
площадки ищет подходящий слот её зала. Без окончания события, при закрытом
событии или отсутствии подходящего окна возвращается null; форма поясняет,
что нужно уточнить календарь/время. Это исправление подсказки кабинета;
полная проверка всех прямых команд бронирования остаётся частью security audit.

Проверки: два новых API regression tests; Playwright `cabinet-performer.spec.ts`
и `flow.spec.ts` — 7 passed (15.5s), включая явный ввод без тарифа на desktop и
390px и отправку указанной суммы в настоящий тестовый API. Скриншоты просмотрены.
Общий seed заявки теперь задаёт будущее полное окно, а smoke каталога проверяет
фактический заголовок «Найдите свою команду». Оба файла сценариев уже входят в CI.

Быстрая заявка из выбранного слота сохраняет также его окончание в новом Event.
`make test-api` — 392 passed, 2 skipped (145.71s). После последней правки
quick-request отдельный прогон `pytest tests/test_request_suggestions.py tests/test_offers.py -q`
— 8 passed (4.34s), включая новый regression этой правки. `make lint`,
`make web-lint`, `make web-build` прошли. Новых миграций нет.

### Права и состояние события при удержании

Одиночный hold требует пишущей роли как у заказчика, так и у исполнителя.
Viewer не может зарезервировать дату даже при исторически установленном
`can_confirm_offer`. Одиночный и atomic hold проверяют, что Event не Completed
и не Cancelled, перед захватом слотов; Event перечитывается под блокировкой
записи, а Booking обновляется из БД перед проверкой статуса.
Отказ не создаёт hold или audit успешного удержания.

Deal Room возвращает `can_hold` с учётом роли, статуса Event/Booking и двух ack.
Это разрешение на попытку; календарь повторно проверяет сама команда.
Настольная кнопка учитывает разрешение. На телефоне после двух ack основная
кнопка переключается на «Удержать дату», а для viewer остаётся неактивной.
Новой миграции нет. Проверка окна события в прямых командах и сериализация
остальных мутаций сделки ещё входят в незавершённый security audit.

Проверки hold: `make test-api` — 399 passed, 2 skipped (160.72s);
после финальной правки текста next_step — 6 focused tests passed (3.38s).
`make lint`, `make web-lint`, `make web-build` прошли.
`npx playwright test e2e/deal-path.spec.ts --grep 'Viewer cannot hold|E08:' --workers=1 --reporter=line`
— 3 passed (12.3s): создание viewer через настоящую тестовую команду,
отказ API, запрет кнопки, успешное действие владельца desktop/390,
сброс ack новой версией и повторное согласование. Скриншоты просмотрены;
сценарии входят в существующий CI-файл deal-path.

### Прямые команды предложения и резерва: окно события

Создание Offer и одиночный/atomic hold повторно проверяют на сервере:
будущее начало, явно указанное окончание позже начала, принадлежность слота
ресурсу заявки, полное покрытие окна с техническими setup/teardown и
календарными буферами, отсутствие busy/held/confirmed пересечений.
Неподходящий слот возвращает 409 до создания предложения или резерва;
подсказка `GET /requests` не заменяет эту проверку.

Для legacy Event без окончания существующий `planning-context` позволяет
явно заполнить его внутри всех связанных слотов. Проверен отказ hold до
уточнения и успешное продолжение после него. Старые цены и quote_id при этом
не переписываются. Новых миграций нет.

Проверки окна: `make test-api` — 413 passed, 2 skipped (119.51s),
включая 14 новых regression cases; `make lint` и `make web-lint` прошли.
Playwright `deal-path.spec.ts flow.spec.ts --grep 'Viewer cannot hold|E08:|заявка → оффер' --workers=1 --reporter=line`
— 5 passed (28.4s). Код web не менялся, использована ранее проверенная production
сборка. Test fixtures теперь задают полное окно и будущие даты там, где
проверяется создание новой сделки; негативные сценарии отдельно проверяют
неизвестное окончание и прошедшее время.

Выявленный диагностическим тестом atomic hold двух пересекающихся legacy-слотов
одного артиста исправлен: проверка пакета отклоняет его до первого захвата.
Добавлены транзакционные блокировки ресурса для календарных writers и отдельные
проверки конкурентных запросов на PostgreSQL. Протокол и ограничения:
[CALENDAR_CONCURRENCY.md](../ops/CALENDAR_CONCURRENCY.md).
Полный security audit остальных мутаций сделки ещё не завершён.

### Проверка конкурентных операций календаря

Полный make test-api с BOOKER_TEST_POSTGRES_URL: 416 passed, 2 skipped (146.02s).
Два concurrency-теста выполнялись на PostgreSQL 16; остальные используют обычные fixtures.
Отдельный прогон atomic/многозального пакета/гонки/PG: 6 passed (4.31s).
Полная цепочка Alembic upgrade head прошла на пустой PostgreSQL базе до b5c6d7e8f9a0.
make lint и make web-lint прошли. Web-код не менялся, использована проверенная production-сборка.
Playwright deal-path.spec.ts с фильтром 'Viewer cannot hold|E08:': 3 passed (19.5s), desktop и 390px.
E08 теперь ждёт ответа hold перед чтением результата. Новый CI job calendar-postgres
проверяет миграции и два concurrency-сценария. YAML проверен локально;
удалённый GitHub Actions в этом блоке не запускался.


### Согласование версии и фиксация резерва

Изменение версии и ack сериализованы с hold блокировкой Event и перечитывают
активный quote после ожидания. Completed/Cancelled Event отклоняет обе команды.
Редактирование может передать expected_quote_id: устаревшая исходная версия
возвращает 409 без создания новой. Hold после выигравшего изменения требует
новых двух ack; после выигравшего hold версия не меняется.

Deal Room передаёт quote_id отображаемых условий при каждом ack. Если другой
участник уже изменил предложение, API отклоняет подтверждение; пользователь
нажимает «Обновить условия», читает новую сумму и подтверждает заново.
Новых миграций и audit-типов нет; используются offer.version / offer.ack.

Проверки согласования: полный make test-api с PostgreSQL URL — 421 passed,
2 skipped (162.69s), включая пять PG concurrency-сценариев.
Отдельные quote/PG проверки — 11 passed (8.58s).
make lint, make web-lint, make web-build прошли.
Playwright deal-path с фильтром 'Stale displayed|Viewer cannot hold|E08:' —
5 passed (12.1s). Скриншоты отказа и кнопки обновления просмотрены на desktop
и 390px; после обновления подтверждается новая серверная сумма.


### Отмена только собственного резерва

Отмена альтернативного предложения больше не освобождает held/confirmed слот
другого бронирования. Проверяется владение и отсутствие других сохраняющих
резерв ссылок; все active hold отменяемой сделки закрываются вместе.
Отмена использует общие блокировки Event/ресурса/слота и перечитывает состояние
после ожидания. Своя отмена и дальнейший подбор замены сохранены.
Миграции, новые endpoints и типы audit не требуются.

Проверки отмены: make test-api с PostgreSQL URL — 424 passed, 2 skipped
(130.31s), включая шесть PG concurrency-сценариев. Отдельные ownership/PG
проверки — 8 passed (8.92s); replacement/lifecycle/ownership — 8 passed (2.91s).
make lint прошёл. Playwright event-replacement.spec.ts — 2 passed (8.7s),
desktop и 390px. Web-код в этом изменении не менялся; использована проверенная
сборка предыдущего блока. Новая PG-проверка входит в существующий CI job.


### Договор: полномочия, действующий резерв и подписи

Создать договор может заказчик с ролью owner/admin/manager. Подписывать свою
сторону могут участники с этими ролями; viewer получает 403 даже при известном
OTP. Новые уведомления с кодами адресуются только участникам с правом записи.
DevTransport скрывает тело contract.otp и auth.password_reset в новых записях
AuditLog; это не очистка исторических записей или хранилища доставки.

Новый договор и новая подпись проверяют активный собственный hold с TTL,
удержанный слот, открытое будущее событие, совместимость интервала и оба ack.
Подпись дополнительно требует AwaitingContract и quote_id из текста договора,
совпадающий с текущей версией. Проверки идут под блокировками Event/ресурса/слота.
Принятая подпись с правильным кодом при повторе возвращает сохранённый результат
без повторных audit, сообщений и перехода к оплате. Rate limit ограничивает
создание и попытки подписи в рамках текущего in-memory механизма API.

Deal Room получает can_create_contract/can_sign_contract от API. Кнопки
учитывают права и состояние. На мобильном экране поле кода доступно в панели
действий; готовый договор подписывается кнопкой «Подписать договор».

Проверки: make test-api с PostgreSQL URL — 431 passed, 2 skipped (157.18s).
Отдельные contract/PG tests — 13 passed (11.69s). Среди семи PG-сценариев
проверены одновременные подписи: оба результата сохраняются, сообщение и
уведомление перехода к оплате создаются один раз, повторы ничего не дублируют.
make lint/web-lint/web-build прошли. Playwright contract permissions/signing
— 2 passed (4.7s), desktop и 390px: viewer без кодов/подписи и реальная подпись
writer. Скриншоты обоих экранов просмотрены. После защиты сравнения OTP от
не-ASCII ввода contract guards повторно прошли: 6 passed (3.03s), включая
отказ 403 вместо ошибки сервера для такого кода.
Миграции не требуются. Production и удалённый CI не запускались.


### Срок версии предложения

Новые OfferVersion имеют `valid_until`: по умолчанию 72 часа от создания,
не позднее начала события. API create offer/new version принимает
`valid_for_hours` (целое 1–720); некорректное значение не создаёт версию.
Срок неизменяем вместе с опубликованными условиями. Миграция
`c6d7e8f9a0b1` добавляет nullable deadline, индекс и receipt уведомления;
историческим версиям срок задним числом не назначается.

В Negotiation истёкшую версию нельзя подтвердить или удержать, в том числе
после ожидания блокировки календаря и в atomic hold. Для новой попытки нужна
новая версия и оба ack. После удержания условия закреплены; acceptance deadline
не отменяет действующий hold или договор. Повторное подтверждение условий
закрытой/закреплённой сделки запрещено. Deal Room возвращает valid_until,
acceptance_expired, can_ack_quote, can_revise_quote и понятный следующий шаг.
Readiness не засчитывает просроченные условия в готовность события.

Вкладка «Условия» позволяет предложить новую сумму, текст и срок 24/72/168 часов,
с привязкой к показанному quote_id. Денежный итог рассчитывает API; прежние
условия остаются в истории. Основные кнопки ack учитывают серверные полномочия.
На desktop и телефоне доступно объяснение истечения и переход к новой версии.
Виджет «Истекающие предложения» артистов и площадок теперь использует срок
условий; активные удержания остаются отдельным виджетом.

Уведомления offer.expired обрабатываются существующим bounded maintenance,
однократно по версии и получателю. Не требуется своевременный worker, чтобы
API отказал в использовании истёкшей версии. Это in-app доставка; внешние
провайдеры и production scheduler не подключались.

Проверки сроков: полный make test-api с PostgreSQL URL — 439 passed, 2 skipped
(142.65s). Отдельные validity/PG — 15 passed (20.75s); после финального
исправления Readiness и текста следующего шага validity/readiness —
19 passed (13.14s). make lint, web-lint и web-build прошли. Playwright
stale quote + contract + expiry revision — 6 passed (13.7s), desktop и 390px.
Скриншоты формы новых условий просмотрены на обоих экранах.
Миграция проверена на существующих SQLite и PostgreSQL тестовых базах.
E2E expiry fixture меняет срок только созданной им версии в disposable SQLite
под /tmp и требует BOOKER_ENVIRONMENT=test; не применять к общей/production БД.
Финальный Playwright повтор expiry revision после обновления API — 2 passed (7.3s).


### Пульт коммерции: тарифы и доступ организаций

`/admin/commerce` связан с главным пультом и использует существующий platform
admin/TOTP guard. Обычный пользователь не получает каталог администратора,
список организаций или возможность управлять чужими подписками.

Интерфейс показывает серверные версии тарифов и редактирует месячную/годовую
цену с обязательной причиной. Сохраняются существующие features и ставки;
expected_version предотвращает перезапись устаревшего каталога. API сохраняет
новую версию и audit commercial.plan_changed; старые заказы/quotes не меняются,
Free не становится платным. Причина из одних пробелов отклоняется.

Новый GET `/admin/commerce/organizations` даёт поиск по ID/названию, limit 1–100,
offset и total. Возвращаются подписка и effective_status: истёкший платный период
не показывается как действующий, даже до maintenance. Чтение не меняет статусы.
Новая форма позволяет выдать manual active/trial/past_due на 1–366 дней через
существующий grant, с причиной и expected_updated_at. Пустой expected_updated_at
означает ожидание отсутствующей подписки; старое состояние получает 409.
Legacy-вызовы grant без этого поля сохраняют прежний контракт.

POST `/admin/commerce/organizations/{id}/revoke` требует текущий updated_at
и причину, блокирует организацию, переводит доступ в cancelled и завершает
период немедленно. Audit subscription.admin_revoke фиксирует причину, план,
прежний статус и отсутствие возврата. Повтор уже отозванного состояния с его
актуальной версией не создаёт второй audit. BillingOrder и деньги не меняются.
Подписка с provider_subscription_id не отзывается/перезаписывается вручную:
сначала нужен отдельный workflow провайдера. Никакого вызова реального PSP нет.

Это часть Admin Commercial Center: сводка выручки и модерация продвижения
остаются отдельной незавершённой частью общего задания. Миграций в этом блоке нет.

Проверки пульта: полный API с PostgreSQL — 441 passed, 2 skipped (176.70s).
Отдельные admin-commercial/commerce — 26 passed (3.84s); make lint, web-lint,
web-build прошли. Playwright admin-commercial — 2 passed (8.3s), desktop/390px:
отказ обычному пользователю, выдача Pro, отзыв до Free, новая версия цены через
форму и проверка публичного каталога. Тестовая цена восстановлена отдельной
версией в finally. Скриншоты обоих экранов просмотрены. Запуск E2E — локально,
одним worker на disposable БД; production и удалённый CI не запускались.


### Коммерческий центр: отчёт и обзор продвижения

GET `/admin/commerce/revenue` и соответствующий блок пульта дают московский
период (по умолчанию последние 30 дней, максимум два года) по **created_at**.
Это когорта записей с их текущими статусами, не cash-flow по дате capture:
у Payment нет полноценного timestamp фактического списания. Показаны группы
платежей и заказов подписок/продвижения по статусу и провайдеру, отдельно
external (подтверждено API), stub (тест) и неизвестные/disabled источники.
Оплаченные, ожидающие и возвращённые записи не суммируются в одну выручку.

GMV — гонорар сохранённой версии условий. Platform fee — её полный snapshot,
без пересчёта по сегодняшнему тарифу. Подтверждённые сделки (Confirmed,
InProgress, Completed) дают начисленную стоимость; DateHeld/AwaitingContract/
AwaitingPayment с действующим hold — ожидаемую. Стоимость разделена по наличию
внешней/тестовой/смешанной оплаты или отсутствию подтверждённой оплаты.
Несколько Payment одной сделки не умножают её стоимость. При недостающей
версии/полной комиссии показываются известные части и счётчики отсутствующих
данных. Суммы сделок не складываются с платежами. Отчёт не заменяет банковскую
сверку и не восстанавливает отсутствующие данные частичных возвратов.

GET `/admin/commerce/campaigns` даёт bounded список (limit 1–100, offset, total),
фильтр draft/pending_payment/scheduled/active/expired/cancelled/rejected,
организацию, профиль, срок и основание продвижения: платёжный заказ, ledger
включённого Boost или неизвестное основание. Истечение выводится по времени
без изменения состояния при GET. Оплаченный заказ у rejected/cancelled кампании
отмечается для проверки оператором, без утверждения о возврате. Это обзор
существующих состояний, а не команда ручного изменения кампании или PSP.
Оба endpoint требуют platform admin и существующий TOTP guard.

В пульте доступны смена периода и пустая выборка, фильтр и пагинация кампаний.
Тесты API проверяют московскую границу суток, права, предел периода, разные
провайдеры/статусы, отсутствие двойного GMV, неизвестную комиссию, действующий
hold, effective expiry и необходимость проверки платежа отклонённой кампании.
Миграций, production-команд и реальных платёжных операций в этом блоке нет.

Проверки: полный API-прогон до финального разделения стоимости сделок по источнику
оплаты — 443 passed, 2 skipped (288.42s). Финальный отчёт/кампании на SQLite —
2 passed (2.95s); тот же финансовый сценарий на PostgreSQL — 1 passed (5.74s),
с границами московского дня, mixed-источником и действующим hold. PG-проверка
входит в существующий CI job через test_calendar_postgres.py. Отдельный ранний
commercial/admin/PG прогон — 34 passed (16.22s). Сборка интерфейса прошла.
Финальный Playwright admin-commercial — 2 passed (19.3s): desktop/390px,
смена периода и пустая выборка, фильтр кампаний, прежние grant/revoke/price
действия. make lint и web-lint прошли. Экраны отчёта просмотрены на обеих ширинах.
Удалённый CI и production не запускались.


## Capture и конкуренция резерва — 15 сентября 2026

Унифицирован порядок блокировок оплаты, отмены и истечения. Подтверждение оплаты
проверяет собственный действующий резерв, открытое событие и сумму quote; конфликт
сохраняет денежный факт и требует оператора, не обещая дату. Истечение после
capture перечитывает consumed hold и не освобождает слот. Создание нового платежа
для закрытого события запрещено. Новых миграций и изменений UI здесь нет.
Readiness E2E теперь задаёт полное окно через форму до создания предложений,
сохраняя проверку неизвестного окна и ошибки загрузки.

Проверено из worktree с PATH=/tmp/booker-prelaunch-tools/bin:$PATH:
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 452 passed, 2 skipped (191.44s).
- Отдельный tests/test_calendar_postgres.py на той же PostgreSQL — 12 passed (23.00s).
- make lint — passed.
- Из apps/web, BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test event-readiness.spec.ts --workers=1 --reporter=line — 2 passed (14.7s), 1440/390.
- event-budget.spec.ts в предыдущем совместном прогоне — 2 passed; readiness в том прогоне падал на устаревшем порядке fixture, исправлен и перепроверен отдельной командой выше.

Полная цель остаётся открыта: checkout receipt, реальное второе подтверждение
возврата, pending/failed refund, нормализация raw webhook и recurring mapping
ещё требуют реализации и проверки. Настоящий PSP не подключался.

## Сохранённая платёжная сессия — 15 сентября 2026

Payment теперь хранит checkout_url, provider_reference и session_state.
Миграция d7e8f9a0b1c2 после c6d7e8f9a0b1 сохраняет старые платежи как ready без
повторного создания сессий. Новый Payment/key коммитится до обращения к партнёру.
При тайм-ауте ответ 502 оставляет uncertain и тот же идентификатор; повтор с другим
UI-ключом передаёт партнёру исходные payment_id/amount/idempotency_key. Адаптер
обязан реализовать идемпотентность на стороне PSP. Сохранённый ready возвращается
без повторного обращения. Ответ checkout не подтверждает деньги.

Проверяется binding provider/payment, pending-статус, HTTPS URL без credentials,
наличие provider_reference при redirect. Секретные URL и ответы ошибок не идут в
audit. Deal Room показывает переход к оплате только writer заказчика, при живом
резерве и включённом исходном провайдере. Для uncertain есть пояснение повтора.
Платёжный режим production остаётся выключенным.

Проверки (из worktree, если не указано иначе):
- Из apps/api: BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test ../../.venv/bin/python -m pytest tests/test_checkout_receipts.py tests/test_payment_guards.py tests/test_payments.py tests/test_external_payment_confirm.py -q — 30 passed (19.41s).
- После финальной проверки выключенного/сменённого провайдера: тот же pytest tests/test_checkout_receipts.py tests/test_payment_guards.py -q — 24 passed (17.41s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres + pytest tests/test_calendar_postgres.py -q — 13 passed (27.13s); новый сценарий доказывает commit до внешнего вызова и ожидание второго checkout.
- Alembic upgrade head на SQLite /tmp/booker-support-e2e.db и отдельной PostgreSQL booker_migrations_52962f288b3e — passed до d7e8f9a0b1c2.
- PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint, make web-lint — passed.
- PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build — passed.
- Из apps/web: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test booking-payment.spec.ts --workers=1 --reporter=line — 5 passed (12.0s). Два настоящих stub-flow desktop/mobile; unavailable UI; два явно обозначенных provider-boundary UI fixtures uncertain/redirect (не PSP acceptance).

Сверка uncertain после закрытия события, проверка raw webhook, реальные два
действия операторов возврата и recurring cycles остаются следующими задачами.

Полный прогон этого блока: PATH=/tmp/booker-prelaunch-tools/bin:$PATH
BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres
BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api —
462 passed, 2 skipped (214.12s). После него финальное ограничение ссылок для
выключенного/сменённого провайдера, прошедшего события, потерянного слота и
истёкшего hold перепроверено командой pytest tests/test_checkout_receipts.py
tests/test_payment_guards.py -q — 27 passed (12.88s); make lint повторно passed.
Полный прогон предшествует добавлению трёх последних reservation cases; их нельзя
включать в указанное число 462. Финальная миграция и UI после build не менялись.

## Возвраты с независимым подтверждением — 15 сентября 2026

Добавлена PaymentRefund и миграция e8f9a0b1c2d3 после d7e8f9a0b1c2.
Старый POST с approver_user_id, который сразу менял статус оплаты, заменён
сохранённым запросом и отдельным approve под сессией другого администратора.
Настроенный TOTP и свежий код обязательны для каждого действия даже при
отключённом общем enforcement. БД запрещает совпадение requester/approver;
перед отправкой перечитываются текущие полномочия обоих операторов.

Новые endpoints `/admin/refunds`: GET (очередь, status/payment_id, limit/offset),
POST (reason, idempotency_key, optional amount_rub), POST /{id}/approve,
/reject, /retry, /refresh, /confirm-external. Они проверяют platform admin,
частоту/размер запросов, состояние, исходного партнёра, сумму и остаток; все
изменения имеют audit. Незавершённый возврат не допускает второй запрос на тот
же платёж. После успешного частичного возврата можно вернуть остаток.

До обращения к провайдеру сохраняются запрос, подтверждение и стабильный ключ.
Pending/failed/uncertain не меняют статус денег на refunded. Только проверенный
succeeded суммирует успешные возвраты и устанавливает partially_refunded/refunded.
Проверяется соответствие amount/kind/reference. Сетевые ошибки не раскрывают
секретный ответ и оставляют uncertain; повтор использует прежний ключ.
Generic get_refund_status служит границей чтения статуса PSP. Реальный партнёр
не подключён. External approve оставляет pending; отдельное действие оператора
с номером проверенного перевода фиксирует фактическое перечисление. Stub явно
тестовый, с детерминированным refund ID; деньги не перечисляет.

Страница `/admin/refunds` связана с пультом оператора. Есть загрузка, ошибка и
повтор, пустая выборка, фильтр/пагинация, форма причины/суммы, ввод TOTP,
независимое подтверждение, отклонение, retry, refresh и external confirmation.
В Deal Room и коммерческом отчёте добавлено русское обозначение частичного
возврата. Мобильный screenshot проверен визуально: текст/ID переносятся,
горизонтального переполнения нет. CSS использует существующие компоненты.

Проверки:
- Из apps/api: BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test ../../.venv/bin/python -m pytest tests/test_refunds.py tests/test_admin.py tests/test_totp_security.py tests/test_payment_adapter.py tests/test_authz_regressions.py -q — 53 passed (19.39s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres + pytest tests/test_calendar_postgres.py -q — 15 passed (24.39s). Две новые гонки: approve/approve и approve/новый возврат; второй запрос действительно ждёт, PSP вызывается один раз.
- Alembic upgrade head на SQLite /tmp/booker-support-e2e.db и отдельной PostgreSQL booker_migrations_52962f288b3e — passed до e8f9a0b1c2d3.
- PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint и make web-lint — passed.
- PATH=/tmp/booker-prelaunch-tools/bin:$PATH NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build — passed.
- Из apps/web: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test admin-refunds.spec.ts --workers=1 --reporter=line — 2 passed (8.0s), 1440/390. Это настоящий local API/DB/stub путь с двумя отдельными администраторами, включая error/empty UI. Две ошибки локаторов в первоначальном прогоне исправлены (route announcer и label, включавший options).
- booking-payment.spec.ts в совместном прогоне — 5 passed; admin-refunds тогда падал только на локаторах, финальный результат выше.
- В CI добавлен admin-refunds E2E. Critical e2e получает те же BOOKER_DATABASE_URL и BOOKER_ENVIRONMENT, что API; fixture использует local venv или установленный python3, только для test SQLite в /tmp. CI на GitHub в этом инкременте не запускался.

Полный первый API-прогон: 1 failed, 477 passed, 2 skipped (245.58s) — оставшийся
старый test_authz_regressions ожидал прежний однозапросный протокол. Он обновлён
с сохранением проверок отказа до оплаты и идемпотентности и прошёл в focused
наборе выше; повторный полный прогон выполняется отдельно.

Оставшаяся работа полной цели включает raw PSP webhook/status reconciliation,
возвраты commerce orders, recurring cycles, оставшиеся уведомления и SEO,
а также итоговую сверку всех разделов мастер-задания. Этот блок не означает
готовность реального эквайринга и не включает юридическое подтверждение.


Финальные проверки возвратов:
- Повтор PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 479 passed, 2 skipped (246.08s).
- После полного прогона добавлены проверка актуальных полномочий, throttle очереди и UNIQUE(provider, provider_reference) с savepoint. Финальный pytest tests/test_refunds.py tests/test_calendar_postgres.py -q — 29 passed (36.25s); дополнительно новый PostgreSQL case `-k refund_reference_is_accounted_once` — 1 passed, 15 deselected (2.98s). Новые случаи не включены в число 479.
- Финальная миграция с UNIQUE проверена downgrade e8f9a0b1c2d3 → d7e8f9a0b1c2 и upgrade head на обеих выделенных тестовых БД. Пересоздавалась только новая таблица тестовых возвратов; production не затрагивался. Это проверка ещё не выпущенной миграции, не инструкция откатывать финансовые данные production.
- make lint и make web-lint — passed; исходный UI после успешной сборки не менялся.
- Повтор admin-refunds.spec.ts на окончательной миграции и API — 2 passed (9.5s), те же 1440/390 и команда выше.

## Проверка исходных платёжных уведомлений — 15 сентября 2026

Новый POST `/payments/provider-webhook` читает исходные bytes (до 64 KiB) и
headers, передаёт их PaymentAdapter.verify_raw_webhook, затем проверяет полный
VerifiedPaymentEvent: payment ID, status, amount_rub, RUB, merchant_id,
provider_reference. Ожидаемый merchant задаётся адаптером из конфигурации,
не берётся из входящего события. Старый JSON POST `/payments/webhook` разрешён
только stub. Отсутствие реализации raw verification даёт 503; неверная подпись
не доходит до доменного перехода. Реальный PSP не выбирался и не подключался.

PaymentWebhookEvent получил fingerprint финансовых полей и provider-scoped
receipt ID. Повтор с теми же нормализованными данными возвращает сохранённый
ответ; изменённые данные конфликтуют. Receipt резервируется до capture/hooks.
Raw payload и подпись не сохраняются в audit. Pending не подтверждает деньги,
late failed не отменяет capture; поздняя оплата после потери hold сохраняет
денежный факт с reservation conflict, не восстанавливая дату. Обработка БД
вынесена в threadpool, чтобы ожидание SQL lock не блокировало async event loop.

Миграция f9a0b1c2d3e4 после e8f9a0b1c2d3 добавляет nullable fingerprint и UNIQUE
index(provider, provider_reference) у Payment. Один reference не может оплатить
два Payment. Первый verified event может восстановить reference после потери
checkout response. Конфликт reference при создании checkout откатывается через
savepoint: запись остаётся uncertain без чужого URL. Исторические дубликаты
миграция не переписывает; такой конфликт потребует сверки до rollout.

Проверки:
- Из apps/api: BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test ../../.venv/bin/python -m pytest tests/test_provider_webhook.py tests/test_payments.py tests/test_payment_guards.py tests/test_checkout_receipts.py tests/test_external_payment_confirm.py -q — 50 passed (16.78s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres + pytest tests/test_provider_webhook.py tests/test_calendar_postgres.py -q — 35 passed (32.61s), включая все 18 PostgreSQL cases; неверный merchant/amount/currency/reference, размер тела, подпись/повторы, закрытый резерв и разные платежи.
- Дополнительный финальный checkout test проверяет конфликт reference при ответе создания сессии: pytest tests/test_checkout_receipts.py -q — 13 passed (9.71s).
- Alembic upgrade head на SQLite /tmp/booker-support-e2e.db и отдельной PostgreSQL booker_migrations_52962f288b3e — passed до f9a0b1c2d3e4.
- PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint — passed.
- Из apps/web: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test booking-payment.spec.ts admin-refunds.spec.ts --workers=1 --reporter=line — 7 passed (14.1s), desktop/390.

Новый raw endpoint проверен через настоящий API test client и PostgreSQL;
браузерный прогон проверяет сохранность существующих путей оплаты и возврата,
не выдаётся за sandbox PSP. В этом блоке не менялись исходники UI; повторная
web-сборка не требовалась. Полная цель остаётся открыта, следующий шаг —
status reconciliation без создания нового checkout и дальнейший recurring mapping.

Полный прогон этого блока: PATH=/tmp/booker-prelaunch-tools/bin:$PATH
BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres
BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api —
502 passed, 2 skipped (250.21s). После старта полного прогона добавлен один
checkout collision test (прошёл в наборе 13 выше) и расширена проверка raw pending:
pytest tests/test_provider_webhook.py tests/test_calendar_postgres.py -k
'signed_original_bytes or verified_payment_event_roundtrip' -q — 2 passed,
33 deselected (4.06s), SQLite + PostgreSQL. Исходная реализация после полного
прогона не менялась; lint повторно passed.

## Сверка существующего платежа — 15 сентября 2026

`PaymentAdapter.get_payment_status(payment_id, provider_reference, idempotency_key)`
добавляет authenticated read внешней границы, без fallback в create_session.
POST `/admin/payments/{id}/reconcile` требует platform admin и обязательно
настроенный TOTP со свежим кодом. Body не позволяет передать статус или сумму.
Запрос аудируется и коммитится перед обращением к партнёру. Ожидание сети не
держит domain locks; после ответа проверяются текущие payment/merchant/amount/RUB/
reference и применяется общий verified-event путь. Повтор финансового состояния
идемпотентен, но результат UI содержит текущие Payment/Booking, а не старый receipt.
Состояния возврата не перезаписываются чтением capture status.

Сверка работает после закрытия/истечения резерва: verified succeeded сохраняется
как деньги с requires_operator, не восстанавливая дату. Неверные реквизиты,
другой платёж, отсутствие TOTP/прав или сетевой сбой не подтверждают оплату.
Реальный PSP не подключён; local stub не выдумывает банковский статус и без
реализации read возвращает недоступность. Положительные ответы тестируются на
границе адаптера, сам domain/API не заменяется моками.

В `/admin` добавлен компонент сверки: пустое состояние, ожидание, ошибка и повтор,
свежий TOTP для каждого чтения, статус у партнёра и в Букере, сумма из API,
флаг расхождения/потери резерва, ссылка на сделку. Deal Room больше не показывает
ожидание создания счёта после полученного capture при старом uncertain receipt.
Браузер выявил прежнее растяжение всей admin grid таблицей каталога на 390px;
локальное `.admin-grid > * { min-width:0; overflow-wrap:anywhere }` удерживает
таблицы внутри имеющихся scroll containers и сохраняет desktop grid.
Мобильный screenshot проверен визуально, текст и форма помещаются.

Проверки из worktree, PATH=/tmp/booker-prelaunch-tools/bin:$PATH:
- BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test pytest tests/test_payment_reconciliation.py tests/test_provider_webhook.py tests/test_payment_guards.py tests/test_checkout_receipts.py -q из apps/api через ../../.venv/bin/python — 54 passed (26.98s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/python -m pytest apps/api/tests/test_payment_reconciliation.py apps/api/tests/test_calendar_postgres.py -q — 28 passed (33.17s). Включает все 19 PostgreSQL cases и отмену во время paused provider read.
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 513 passed, 2 skipped (203.15s).
- make lint, make web-lint — passed.
- NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build — passed; после исправления mobile grid повторно passed.
- Из apps/web: BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test payment-reconciliation.spec.ts booking-payment.spec.ts --workers=1 --reporter=line — 6 passed, 1 failed (12.4s), обнаружено mobile overflow.
- После исправления той же командой только payment-reconciliation.spec.ts — 2 passed (6.5s), 1440/390, включая keyboard submit. Пять booking-payment scenarios прошли в совместном прогоне; их поведение не менялось исправлением admin CSS.

Новый E2E добавлен в CI critical suite. Его ответы статуса явно являются UI
provider-response fixtures; реальные authorization/domain transitions проверены
API и PostgreSQL выше. Это не sandbox acceptance настоящего PSP. Новых миграций
нет: БД остаётся на f9a0b1c2d3e4. Полная цель открыта: raw refund mapping,
recurring и оставшиеся пункты master acceptance требуют дальнейшей работы.


### Подписанные уведомления о booking refund — 2026-09-15

Реализованы `VerifiedRefundEvent`, fail-closed adapter method и
`POST /payments/refund-provider-webhook`. Связь с сохранённой командой проверяется
по исходному idempotency key, Payment/reference, provider, merchant, валюте и сумме.
Учитываются только независимо согласованные и отправленные запросы. Timeout
восстанавливается из проверенного события; повтор, чужие реквизиты и запоздалый
pending не увеличивают сумму и не отменяют результат. Неизвестный refund и
противоречивые terminal outcomes требуют сверки (409). Реальный PSP не подключён.

Новых миграций/UI нет: receipts используют payment_webhook_events с отдельным
namespace, итог доступен в существующем `/admin/refunds` и Payment API.
Проверки из apps/api с BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test:
- ../../.venv/bin/python -m pytest tests/test_refund_webhook.py tests/test_refunds.py tests/test_provider_webhook.py -q — 49 passed (31.19s).
- С BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres: ../../.venv/bin/python -m pytest tests/test_calendar_postgres.py -k refund -q — 4 passed, 16 deselected (5.72s); два concurrent callbacks учитываются один раз.
- Из worktree: PATH=/tmp/booker-prelaunch-tools/bin:$PATH make lint — passed.
- Полный API-прогон из worktree: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 532 passed, 2 skipped (222.54s); PostgreSQL включён.

UI не менялся, browser/build проверки этого изменения повторно не заявляются.
Общая цель остаётся открытой: следующий этап — billing cycle / recurring и полный
аудит остальных требований разделов 0–35.

### Сохранение commerce checkout до вызова партнёра — 2026-09-15

Подписки и платное продвижение теперь сохраняют BillingOrder, цену/snapshot,
связанную Subscription/PromotionCampaign и состояние создаваемой сессии до
внешнего вызова. Повтор использует исходный order.id как ключ PSP и не создаёт
вторую сессию. Timeout оставляет created/uncertain без платного доступа; отмена
неопределённого заказа запрещена до восстановления результата. Provider нельзя
заменить в существующем заказе. Готовый checkout возвращается без нового вызова.

POST /commerce/orders/{id}/checkout: object auth + billing owner/admin + rate
limit + audit. UI кабинета и продвижения: русское сообщение, восстановление
ссылки, disabled во время запроса, ошибка и повтор с клавиатуры. Checkout URL
проверяется как HTTPS без userinfo; paid из create checkout не принимается.
Подписке нужен сохранённый subscription_reference. Миграция не нужна — metadata.

Проверки из worktree с PATH=/tmp/booker-prelaunch-tools/bin:$PATH:
- BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/python -m pytest apps/api/tests/test_commerce.py -q — 30 passed (4.92s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/python -m pytest apps/api/tests/test_commerce.py apps/api/tests/test_paid_promotion.py apps/api/tests/test_calendar_postgres.py -q — 62 passed (44.92s), включая concurrent retries и все 21 PostgreSQL case.
- make lint, make web-lint — passed.
- NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build — passed.
- Из apps/web: BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test commercial.spec.ts promotions.spec.ts --workers=1 --reporter=line — 13 passed, 1 failed (37.9s); имя commercial.spec.ts также выбрало admin-commercial.spec.ts. Ошибка нового mobile теста: неоднозначный role=alert из-за Next route announcer.
- После уточнения селектора: та же команда с commercial.spec.ts -g 'Checkout recovery' — 2 passed (12.6s), 1440/390, ошибка+keyboard retry; screenshot 390 проверен визуально, overflow отсутствует.

UI timeout — явно отмеченная response fixture; сохранение заказа, проверка прав
и тайм-ауты партнёра доказаны API/PG отдельно. Реальный PSP не подключён. Новые
сценарии входят в уже включённый в CI commercial.spec.ts. Общая цель открыта:
расчётные периоды/recurring и полный финальный аудит ещё впереди.
- Полный прогон: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 540 passed, 2 skipped (272.90s). Все текущие API-изменения включены.

### Расчётные периоды и recurring mapping — 2026-09-15

Миграция `a0b1c2d3e4f5_subscription_periods`: subscriptions.agreement_order_id;
billing_orders.subscription_parent_id, period_start/end, entitlement_eligible;
UNIQUE(provider, provider_reference), UNIQUE(parent, period_start). Исторические
даты не выдумываются. Старые строки без подтверждённых period fields продолжают
работать до прежней границы, но не используются для автоматического renewal mapping.

Первый paid сохраняет фактический paid_at (не-test adapter обязан его передать).
POST /commerce/renewal-webhook через verify_renewal_webhook принимает подтверждённый
цикл: original order/subscription/payment binding, fixed snapshot price, integer RUB,
aware dates и календарные границы исходной годовщины. Отдельный заказ на каждый
цикл; повтор и late failed не увеличивают сумму и не отменяют paid. Future paid
открывается только в оплаченный интервал, gap остаётся Free. Past_due не даёт
платных прав, поддерживает отмену будущих попыток. Новый тариф сначала прекращает
предыдущее автопродление. Оплата прекращённого/заменённого соглашения сохраняется
для оператора без активации старого тарифа. UI показывает даты и требует сверку.

Проверки:
- Из worktree, BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/python -m pytest apps/api/tests/test_subscription_cycles.py apps/api/tests/test_commerce.py -q: первый прогон 41 passed/1 failed (11.54s). Старый expiry test вручную менял кеш Subscription; после введения paid-period ledger тест переведён на реальное продвижение clock.
- Затем с apps/api/tests/test_paid_promotion.py: 53 passed (16.66s).
- BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test .venv/bin/python -m pytest apps/api/tests/test_subscription_cycles.py apps/api/tests/test_calendar_postgres.py -q — 35 passed (39.16s) до последнего PG race case.
- Та же среда, pytest apps/api/tests/test_calendar_postgres.py -k duplicate_renewal -q — 1 passed, 21 deselected (1.78s): два simultaneous callbacks создают один оплаченный период.
- Полный финальный API: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api — 556 passed, 2 skipped (205.94s), все текущие API-изменения и 22 PostgreSQL cases.
- make lint, make web-lint — passed.
- NEXT_PUBLIC_API_URL=http://127.0.0.1:8013 BOOKER_INTERNAL_API_URL=http://127.0.0.1:8013 make web-build — passed; финальный build включает доступность отмены при past_due/expired и уточнение сохранения оплаченных периодов.
- Из apps/web: PATH=/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_DATABASE_URL=sqlite:////tmp/booker-support-e2e.db BOOKER_ENVIRONMENT=test BOOKER_COMMERCE_WEBHOOK_SECRET=local-test-only-commerce-webhook-secret BOOKER_API_URL=http://127.0.0.1:8013 BOOKER_WEB_URL=http://127.0.0.1:3013 npx playwright test subscription-cycles.spec.ts commercial.spec.ts --workers=1 --reporter=line — 14 passed (18.7s), включая admin-commercial по имени. Новые циклы проходят настоящий signed stub receiver; реальные деньги не списываются. Screenshot 390 проверен визуально. Новый E2E включён в CI.
- Alembic upgrade head: существующий SQLite e2e DB + PostgreSQL migration DB; downgrade f9a0b1c2d3e4 → upgrade head на PostgreSQL и отдельном SQLite /tmp/booker-cycle-migration.db прошли. Отдельный SQLite также прошёл весь путь baseline → head.

Граница провайдера остаётся внешней: реальный merchant/signature/consent mapping,
PSP sandbox acceptance и live-gates допуска не выполнены. Общая цель открыта до
финального аудита commerce refund mapping, adapter registration, SEO, notification
coverage и остальных требований 0–35.
