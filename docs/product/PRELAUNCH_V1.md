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
