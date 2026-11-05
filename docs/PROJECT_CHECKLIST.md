# BUKERGO — PROJECT CHECKLIST

Автогенерация: `2026-11-05 12:03 UTC` из [`docs/progress/tasks.json`](progress/tasks.json).
Не редактировать вручную — меняйте `tasks.json` и запускайте `python3 scripts/progress_recalc.py`.

## BUKERGO — PROJECT PROGRESS

- Всего: **135** задач
- Выполнено: **89**
- В работе: **4**
- Ожидают: **10**
- Заблокировано: **27**
- Отложено: **5**
- Общая готовность: **65.93%**
- MVP: **84.51%** (60/71)
- Дизайн: **41.67%** (5/12)
- Полный запуск (FULL): **65.15%** (86/132)
- Инфраструктура/релиз (INFRA): **66.67%** (18/27)
- Следующая задача: **ART-07** / Artist vNext IA / 10 сторибордов — утверждение и перенос (без Identity redesign)

### Исторические взвешенные шкалы (не пересчитываются этой формулой)

- На 2026-10-02: FULL **59.0%** / MVP **56.0%** / Design **15.0%**
- Фиксированные веса PROJECT_PROGRESS.md до введения task-count формулы. Сохраняются как история, не пересчитываются.

## Сводка по направлениям

| Направление | Всего | ✅ | 🔄 | ⬜ | ⛔ | ⏸ | % |
|---|---:|---:|---:|---:|---:|---:|---:|
| Архитектура и инфраструктура | 9 | 8 | 0 | 0 | 0 | 1 | 88.89% |
| Авторизация, пользователи, организации и права | 9 | 4 | 0 | 2 | 3 | 0 | 44.44% |
| Кабинет заказчика | 4 | 4 | 0 | 0 | 0 | 0 | 100.00% |
| Кабинет артиста | 7 | 6 | 1 | 0 | 0 | 0 | 85.71% |
| Кабинет площадки | 3 | 3 | 0 | 0 | 0 | 0 | 100.00% |
| Каталог и поиск | 8 | 6 | 0 | 0 | 2 | 0 | 75.00% |
| Календарь и бронирования | 9 | 9 | 0 | 0 | 0 | 0 | 100.00% |
| Заявки, предложения и Deal Room | 6 | 6 | 0 | 0 | 0 | 0 | 100.00% |
| Сообщения и уведомления | 3 | 2 | 0 | 0 | 1 | 0 | 66.67% |
| Платежи, возвраты и выплаты | 12 | 7 | 0 | 1 | 1 | 3 | 58.33% |
| Споры, арбитраж и поддержка | 5 | 4 | 0 | 0 | 0 | 1 | 80.00% |
| Отзывы, рейтинг и аналитика | 3 | 3 | 0 | 0 | 0 | 0 | 100.00% |
| UI/UX, адаптивность и дизайн | 16 | 7 | 3 | 1 | 5 | 0 | 43.75% |
| Безопасность и тестирование | 14 | 12 | 0 | 0 | 2 | 0 | 85.71% |
| Staging, production и релиз | 18 | 3 | 0 | 4 | 11 | 0 | 16.67% |
| Документация и юридические требования | 9 | 5 | 0 | 2 | 2 | 0 | 55.56% |

## Следующие приоритеты

- 🔄 `ART-07` [FULL,DESIGN] — Artist vNext IA / 10 сторибордов — утверждение и перенос (без Identity redesign)
- 🔄 `D03` [FULL] — Согласованные экраны и состояния перенесены в Figma и web
- 🔄 `V04` [DESIGN,FULL] — В дизайн-проекте завершены desktop/mobile макеты и состояния ключевых путей
- 🔄 `V07` [DESIGN,FULL] — Web принят по адаптивности, доступности и скорости
- ⬜ `REL-STAGING-HOST` [MVP,FULL,INFRA] — Owner GO на Infrastructure C / remote staging host
- ⬜ `OWN-SMTP` [MVP,FULL] — Owner предоставил рабочий SMTP для staging/prod notifications
- ⬜ `OWN-TWO-APPROVER` [MVP,FULL] — Два утверждающих для staff recovery приняты
- ⬜ `LEG-03` [FULL] — Хостинг 152-ФЗ / уведомление РКН

## Полный чек-лист

### 1. Архитектура и инфраструктура

- ✅ **ARCH-01** [MVP, FULL, INFRA] Базовый стек Next.js + FastAPI + SQLAlchemy/Alembic в репозитории  <br/>status=`DONE`; evidence: apps/api; apps/web
- ✅ **ARCH-02** [MVP, FULL, INFRA] Alembic цепочка single-head и schema-release manifest  <br/>status=`DONE`; evidence: infra/schema-release-manifest.v1.json; test_schema_release.py
- ✅ **ARCH-03** [MVP, FULL, INFRA] Локальный PostgreSQL 16 test runtime + TEST_POSTGRES_DSN harness  <br/>status=`DONE`; evidence: apps/api/tests/postgres_harness.py; docs/ops/evidence/2026-11-02-v0-safe-hold-expire.md
  - notes: User-space PG 16.15 :55432; не production
- ⏸ **ARCH-04** [FULL, INFRA] PostgreSQL cutover production/staging выбранной БД  <br/>status=`DEFERRED`; evidence: —
  - blocked_by: REL-STAGING-HOST
  - notes: SQLite pilot допустим; restore выбранного engine обязателен
- ✅ **ARCH-05** [INFRA, MVP] Fail-closed staging preflight + негативные тесты  <br/>status=`DONE`; evidence: infra/test_staging_preflight.py
- ✅ **ARCH-06** [INFRA] Staging package hardened (локальный пакет)  <br/>status=`DONE`; evidence: docs/ops/evidence/2026-10-15-staging-hardened.md
  - notes: Host GO ещё нужен
- ✅ **O01** [FULL, INFRA] Локальный sealed backup/SQLite restore evidence v2 проверен  <br/>status=`DONE`; evidence: docs/ops/BACKUP_SEALED.md
- ✅ **O02** [FULL, INFRA] Локальные rollback и schema release gates проверены  <br/>status=`DONE`; evidence: docs/ops/SCHEMA_RELEASE_PLAN_2026-10-02.md
- ✅ **O03** [FULL, INFRA] Локальный монитор и сигналы подготовлены  <br/>status=`DONE`; evidence: docs/ops/OBSERVABILITY_2026-10-02.md

### 2. Авторизация, пользователи, организации и права

- ✅ **AUTH-01** [MVP, FULL] Регистрация с legal pack / draft acknowledgement  <br/>status=`DONE`; evidence: apps/api/tests/; 0bd7aa0 registration wiring
- ✅ **AUTH-02** [MVP, FULL] Организации, роли owner/admin/manager/viewer, переключение workspace  <br/>status=`DONE`; evidence: ROADMAP.md phase 1
- ✅ **AUTH-03** [MVP, FULL] Сессии, 2FA/TOTP storage (hashed/encrypted) локально  <br/>status=`DONE`; evidence: alembic a04f56b78c90; test_totp_storage.py
- ⛔ **AUTH-04** [FULL] Внешние identity bindings (Telegram/Яндекс/VK) — полный единый аккаунт  <br/>status=`BLOCKED`; evidence: IDENTITY_SUPPORT_INVESTOR_GOAL_2026-10-02.md; GET /me/identities + LinkedIdentities profile UI; fail-closed /auth/{yandex,vk}/{start,callback}; docs/ops/SESSIONS_SELF_SERVICE_2026-11-03.md; docs/ops/SESSION_CLIENT_METADATA_2026-11-03.md; tests/test_sessions_self_service.py + test_identity.py (17 PASS local suite); PR #28 CI green through 2d4e4d6+
  - blocked_by: OWN-OAUTH-YANDEX-VK, REL-STAGING
  - notes: Локально готовы: Telegram link/unlink, sessions, Yandex/VK fail-closed stubs. Для DONE нужны: OWN-OAUTH-YANDEX-VK и apply миграции c13a45b67c89 на staging (через REL-STAGING).
- ✅ **AUTH-05** [MVP, FULL, INFRA] Object-level authz regressions покрыты тестами  <br/>status=`DONE`; evidence: test_authz_regressions.py
- ⬜ **OWN-OAUTH-YANDEX-VK** [FULL] Owner предоставил Yandex/VK OAuth client_id и client_secret  <br/>status=`TODO`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; docs/ops/SECRETS_INTAKE_OAUTH_SMTP_2026-11-05.md
  - notes: GO на предоставление есть; значений секретов нет. Intake doc.
- ⬜ **OWN-TWO-APPROVER** [MVP, FULL] Два утверждающих для staff recovery приняты  <br/>status=`TODO`; evidence: docs/ops/evidence/2026-10-15-two-approver-design.md
  - notes: Design+tests flag OFF; SMTP BLOCKED
- ⛔ **S06** [FULL] Сброс пароля, email и первичный TOTP администратора безопасны end-to-end  <br/>status=`BLOCKED`; evidence: docs/ops/STAFF_RECOVERY_2026-10-02.md
  - blocked_by: REL-SMTP, OWN-TWO-APPROVER
- ⛔ **T07** [MVP, FULL] Восстановление доступа администратора, email и TOTP принято (два утверждающих + SMTP + staging)  <br/>status=`BLOCKED`; evidence: docs/ops/STAFF_RECOVERY_2026-10-02.md
  - blocked_by: REL-SMTP, OWN-TWO-APPROVER, REL-STAGING-HOST
  - notes: Локальные offline codes есть; для приёмки: SMTP + two-approver + staging.

### 3. Кабинет заказчика

- ✅ **CUST-01** [MVP, FULL] Кабинет заказчика: события, заявки, holds widgets  <br/>status=`DONE`; evidence: apps/web/app/cabinet/; e2e cabinets
- ✅ **CUST-02** [MVP, FULL] Event Studio: состав/requirements qty и PUT  <br/>status=`DONE`; evidence: ROADMAP C1
- ✅ **P02** [FULL] Event Studio и Control Room локально (FULL)  <br/>status=`DONE`; evidence: apps/web/app/events/
- ✅ **T02** [MVP, FULL] Event Studio и Control Room работают локально  <br/>status=`DONE`; evidence: docs/PROJECT_STATE.md; apps/web/app/events/

### 4. Кабинет артиста

- ✅ **ART-01** [MVP, FULL] Кабинет артиста: базовый dashboard, заявки, календарь overview  <br/>status=`DONE`; evidence: PerformerCabinetDashboard.tsx
- ✅ **ART-02** [MVP, FULL] Артист: PATCH/DELETE тарифов API + UI  <br/>status=`DONE`; evidence: feat/v2-artist-profile-services 8019d56; test_artist_tariff_crud.py
- ✅ **ART-03** [MVP, FULL] Артист: publication-evidence + publication toggle в кабинете  <br/>status=`DONE`; evidence: PublicationWidget.tsx; 8019d56
- ✅ **ART-04** [MVP, FULL] Артист: PATCH профиля/райдера + media_url в search  <br/>status=`DONE`; evidence: test_artist_profile_patch.py; 8019d56
- ✅ **ART-05** [MVP, FULL] Артист: services PATCH/DELETE, sync-tariff, multi-artist selector  <br/>status=`DONE`; evidence: 1944b37; test_service_crud_v2.py
- ✅ **ART-06** [MVP, FULL] Артист: запрос верификации из кабинета (supply→admin)  <br/>status=`DONE`; evidence: apps/api/booker_api/routers/catalog.py POST /artists/{id}/verification-request; apps/api/tests/test_artist_verification_request.py; apps/web/components/cabinet/performer/widgets/PortfolioRiderWidget.tsx; docs/ops/evidence/2026-11-02-art06-verification-request.md
  - notes: Supply request → Verification queued; admin decide closes queue; cabinet CTA
- 🔄 **ART-07** [FULL, DESIGN] Artist vNext IA / 10 сторибордов — утверждение и перенос (без Identity redesign)  <br/>status=`IN PROGRESS`; evidence: docs/design/ARTIST_VNEXT_STORYBOARD_DRAFT_2026-11-03.md; g0 plan D01 DRAFT; docs/design/ART07_ROUTE_AUDIT_DRAFT_2026-11-05.md; docs/design/previews/artist-vnext-storyboards.html; docs/design/previews/index.html (ART-07 card); OWN-DESIGN-ACK 2026-11-05 DRAFT IA; apps/web/lib/onboardingChecklists.ts (Витрина/Слот/Готовность); apps/web/components/cabinet/performer/PerformerCabinetDashboard.tsx (draft banner); docs/ops/STAGING_HOST_INTAKE_2026-11-05.md
  - notes: IN PROGRESS: DRAFT pack + runtime IA (checklist/draft banner). НЕ DONE — pixel Figma + полный V05 transfer.

### 5. Кабинет площадки

- ✅ **VEN-01** [MVP, FULL] Кабинет площадки: базовый dashboard и залы  <br/>status=`DONE`; evidence: ROADMAP C3; cabinet venue
- ✅ **VEN-02** [MVP, FULL] Площадка: верификация venues в админке  <br/>status=`DONE`; evidence: ROADMAP C4
- ✅ **VEN-03** [MVP, FULL] Площадка: доработки publication/photos UX на уровне артистского паритета  <br/>status=`DONE`; evidence: apps/api/booker_api/routers/catalog.py get_venue publication fields; apps/web/components/cabinet/venue/widgets/VenuePhotosWidget.tsx; apps/web/components/cabinet/venue/widgets/VenuePublicationWidget.tsx; apps/api/tests/test_halls.py; docs/ops/evidence/2026-11-03-ven03-venue-publication-ux.md
  - notes: Cabinet photos+publication widgets; owner GET publication_* parity

### 6. Каталог и поиск

- ✅ **CAT-01** [MVP, FULL] Публичный поиск/фильтры и пагинация локально  <br/>status=`DONE`; evidence: test_catalog_search_pagination.py
- ✅ **CAT-02** [MVP, FULL] Publication eligibility gate для artist/venue  <br/>status=`DONE`; evidence: publication_eligibility.py; test_publication_eligibility.py
- ✅ **CAT-03** [MVP, FULL] Публичные услуги /services/public discovery в web  <br/>status=`DONE`; evidence: apps/api/booker_api/routers/services.py list_public_services; apps/web/app/search/page.tsx kind=service; apps/web/components/ServiceResultCard.tsx; apps/api/tests/test_services.py::test_public_services_enrich_profile_and_filter_city_budget; docs/ops/evidence/2026-11-03-cat03-public-services-discovery.md
  - notes: Web /search?kind=service + city/budget filters + profile enrichment
- ✅ **P01** [FULL] Поиск, каталог и профили работают локально (FULL)  <br/>status=`DONE`; evidence: test_catalog_search_filters.py
- ⛔ **P07** [FULL] Каталог измерен на представительном supply (staging)  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING
  - notes: Локальный bench есть; staging.bukergo.ru недоступен (connect fail 2026-11-03). Нужны staging p95/EXPLAIN/mobile HAR на фактическом supply.
- ✅ **S03** [FULL, MVP] Серверный критерий публикации реализован локально  <br/>status=`DONE`; evidence: publication_eligibility.py
- ✅ **T01** [MVP, FULL] Каталог, поиск и профили работают локально  <br/>status=`DONE`; evidence: apps/api/tests/test_catalog_search_filters.py; apps/web/e2e/search-filters.spec.ts
- ⛔ **T09** [MVP, FULL] Каталог измерен на представительном supply и мобильных устройствах (staging p95/EXPLAIN/HAR)  <br/>status=`BLOCKED`; evidence: infra/catalog_bench_local.py
  - blocked_by: REL-STAGING
  - notes: Локальный bench есть; staging.bukergo.ru недоступен (connect fail 2026-11-03). Нужны staging p95/EXPLAIN/mobile HAR на фактическом supply.

### 7. Календарь и бронирования

- ✅ **CAL-01** [MVP, FULL] Создание open-слотов и буферы overlap  <br/>status=`DONE`; evidence: test_slot_buffers.py
- ✅ **CAL-02** [MVP, FULL] Vacation/iCal busy overlays  <br/>status=`DONE`; evidence: test_vacation.py; SupplyCabinetSection
- ✅ **CAL-03** [MVP, FULL] Hold exclusivity: один победитель на слот  <br/>status=`DONE`; evidence: test_hold_race.py
- ✅ **CAL-04** [MVP, FULL] V0-SAFE-HOLD-EXPIRE: атомарный expire exclusive states + late payment review  <br/>status=`DONE`; evidence: fix/v0-safe-hold-expire 8dd2f67; test_hold_expire_v0.py; test_hold_expire_postgres.py 6 PASS
- ✅ **CAL-05** [MVP, FULL, INFRA] PostgreSQL concurrency proofs для hold expire/confirm  <br/>status=`DONE`; evidence: 14 postgres_integration PASS; 8dd2f67
- ✅ **CAL-06** [MVP, FULL] DELETE open slots + slot_is_bookable для offer/quick-request  <br/>status=`DONE`; evidence: feat/v3-calendar-requests 0066bb6; test_slot_delete_and_bookable.py
- ✅ **CAL-07** [MVP, FULL] Port V0+V3 calendar/hold fixes в delivery/live canonical  <br/>status=`DONE`; evidence: cherry-pick 94d7ac4/8dd2f67/0066bb6 onto feat/v4-offer-versions-audit; apps/api/tests/test_hold_expire_v0.py; apps/api/tests/test_slot_delete_and_bookable.py; PR #28 merge 3f52b582309fe95d23a6b402870c7739f319270b; docs/ops/OWNER_GO_EXECUTION_2026-11-05.md
  - notes: Port в master через merge PR #28 (OWN-GIT-INTEGRATION-GO).
- ✅ **P03** [FULL] Оффер/hold/бронь защищены локальными тестами (FULL)  <br/>status=`DONE`; evidence: test_hold_race.py
- ✅ **T03** [MVP, FULL] Версии оффера, hold и запрет двойной брони проверены локально  <br/>status=`DONE`; evidence: apps/api/tests/test_hold_race.py

### 8. Заявки, предложения и Deal Room

- ✅ **DEAL-01** [MVP, FULL] Заявки, офферы с quote_id, ack обеих сторон  <br/>status=`DONE`; evidence: test_offers.py; LAUNCH_CHECKLIST
- ✅ **DEAL-02** [MVP, FULL] Deal Room вкладки чат/условия/документы/платежи/спор  <br/>status=`DONE`; evidence: LAUNCH_CHECKLIST; apps/web/app/deals/
- ✅ **DEAL-03** [MVP, FULL] V4: усиление версий условий, статусов и аудита изменений оффера  <br/>status=`DONE`; evidence: apps/api/booker_api/routers/deals.py; apps/api/tests/test_deal_offer_audit_v4.py; apps/web/app/deals/[id]/page.tsx; apps/web/e2e/deal-path.spec.ts; docs/ops/evidence/2026-11-02-v4-offer-versions-audit.md
  - notes: V4 local PASS: version history, clear accepted, system+audit, immutability, web quote_id
- ✅ **M03** [FULL, MVP] Неизменяемый технический снимок договора/ack локально  <br/>status=`DONE`; evidence: CONTRACT_DRAFT_ACK_2026-10-02.md
- ✅ **P04** [FULL] Deal Room и кабинеты локально (FULL)  <br/>status=`DONE`; evidence: apps/web/app/deals/
- ✅ **T04** [MVP, FULL] Deal Room и кабинеты сторон работают локально  <br/>status=`DONE`; evidence: apps/web/app/deals/; docs/PROJECT_STATE.md

### 9. Сообщения и уведомления

- ✅ **MSG-01** [MVP, FULL] Коммерческий чат deal conversation  <br/>status=`DONE`; evidence: deals conversation routes
- ✅ **MSG-02** [MVP, FULL] User notifications inbox (recipient-indexed)  <br/>status=`DONE`; evidence: alembic a05f67c89d01
- ⛔ **MSG-03** [FULL] Внешняя доставка уведомлений (email/Telegram) включена и проверена  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-SMTP

### 10. Платежи, возвраты и выплаты

- ✅ **M01** [FULL, MVP] Серверный расчёт цены и привязка принятой версии  <br/>status=`DONE`; evidence: pricing.py; CONTRACT.md
- ✅ **M04** [FULL] External evidence отделяет сообщения сторон от денежного факта  <br/>status=`DONE`; evidence: EXTERNAL_PAYMENT_CORRECTION_2026-10-02.md
- ✅ **M05** [FULL] Отмена и возврат блокируют повтор и сохраняют денежный след локально  <br/>status=`DONE`; evidence: CANCELLATION_REFUND_GATES_2026-10-02.md
- ⛔ **M07** [FULL] Партнёр письменно подтвердил схему платежей/чеков/получателей  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-PAY-PARTNER
- ⏸ **M08** [FULL] Live adapter, refund recovery и sandbox money E2E приняты  <br/>status=`DEFERRED`; evidence: —
  - blocked_by: M07, M06
  - notes: stub/external only до Payment Architecture GO
- ⬜ **OWN-PAY-PARTNER** [FULL] Платёжный партнёр письменно подтвердил схему  <br/>status=`TODO`; evidence: —
- ✅ **PAY-01** [MVP, FULL] Stub/external payment + signed webhook + idempotency локально  <br/>status=`DONE`; evidence: test_payments.py; LAUNCH_CHECKLIST
- ✅ **PAY-02** [MVP, FULL] Отказ платежа не подтверждает бронь  <br/>status=`DONE`; evidence: test_payments.py
- ✅ **PAY-03** [FULL] Cancellation/refund gates локально  <br/>status=`DONE`; evidence: CANCELLATION_REFUND_GATES
- ✅ **PAY-04** [FULL] Reconciliation/provider report tables и гонки import  <br/>status=`DONE`; evidence: test_postgres_integration reconciliation
- ⏸ **PAY-05** [FULL] V6 Payment Foundation live adapter (после Legal+Payment GO)  <br/>status=`DEFERRED`; evidence: —
  - blocked_by: OWN-LEGAL-GO, OWN-PAY-PARTNER
- ⏸ **PAY-06** [FULL] V7 Payouts eligibility и реквизиты  <br/>status=`DEFERRED`; evidence: —
  - blocked_by: PAY-05

### 11. Споры, арбитраж и поддержка

- ✅ **P05** [FULL] Поддержка и споры локально (FULL)  <br/>status=`DONE`; evidence: SUPPORT_OPERATOR_QUEUE_2026-10-02.md
- ✅ **SUP-01** [MVP, FULL] Support tickets, operator queue, CAS, SLA window config  <br/>status=`DONE`; evidence: SUPPORT_OPERATOR_QUEUE; SLA.md
- ✅ **SUP-02** [MVP, FULL] Disputes queue/evidence/SLA локально  <br/>status=`DONE`; evidence: disputes migration/API
- ⏸ **SUP-03** [FULL] V8: полный арбитражный контур с уведомлениями и связью с возвратами  <br/>status=`DEFERRED`; evidence: —
  - notes: База есть; расширение после payments
- ✅ **T05** [MVP, FULL] Переписка, поддержка и операторская очередь работают локально  <br/>status=`DONE`; evidence: docs/ops/SUPPORT_OPERATOR_QUEUE_2026-10-02.md

### 12. Отзывы, рейтинг и аналитика

- ✅ **REV-01** [FULL] Reviews API для Completed bookings  <br/>status=`DONE`; evidence: reviews table migration
  - notes: Cabinet UI voluntary per D09
- ✅ **REV-02** [FULL] V9: двусторонние отзывы, репутация, аналитика кабинетов  <br/>status=`DONE`; evidence: docs/ops/REVIEWS_REPUTATION_V9_2026-11-03.md; apps/api/booker_api/review_facts.py; apps/api/tests/test_reviews.py (10 PASS); DealReviewPanel + OrgReviewsBlock + ReputationWidget
  - notes: Local only; stars gated at 10 reviews per CONTRACT
- ✅ **REV-03** [MVP, FULL] Analytics taxonomy + Control Room polish  <br/>status=`DONE`; evidence: ROADMAP C6

### 13. UI/UX, адаптивность и дизайн

- ✅ **D01** [FULL] Атлас экранов и карта переходов (FULL)  <br/>status=`DONE`; evidence: SCREEN_REFERENCE_ATLAS.md
- ✅ **D02** [FULL] Статичный дизайн ключевых путей явно утверждён владельцем  <br/>status=`DONE`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; OWN-DESIGN-ACK
  - notes: Закрыто через OWN-DESIGN-ACK 2026-11-05.
- 🔄 **D03** [FULL] Согласованные экраны и состояния перенесены в Figma и web  <br/>status=`IN PROGRESS`; evidence: ART-07 runtime IA slice 2026-11-05: onboarding copy + performer draft banner
  - notes: IN PROGRESS soft: частичный IA transfer без pixel Figma. НЕ DONE до полного Figma+web.
- ✅ **D04** [FULL, DESIGN] Направление «Рамка слота» и интерактивный черновик motion  <br/>status=`DONE`; evidence: MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md
- ⛔ **D05** [FULL] Конкретный motion утверждён и интегрирован  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-MOTION-ACK
- ⛔ **D06** [FULL] Motion принят по доступности и мобильному E2E  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: D05
- ✅ **OWN-DESIGN-ACK** [DESIGN, FULL] Владелец утвердил статичный дизайн ключевых путей  <br/>status=`DONE`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; docs/design/V04_KEY_PATH_STATE_MATRIX_DRAFT_2026-11-03.md; docs/design/V04_WIREFRAME_HOME_DEAL_STATES_DRAFT_2026-11-03.md; docs/design/V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_DRAFT_2026-11-03.md; docs/design/ARTIST_VNEXT_STORYBOARD_DRAFT_2026-11-03.md
  - notes: ACK на DRAFT wireframe/IA pack ключевых путей. Motion отдельно. V04 pixel Figma ещё открыт.
- ⬜ **OWN-MOTION-ACK** [DESIGN, FULL] Владелец утвердил конкретный motion «Рамка слота»  <br/>status=`TODO`; evidence: docs/ops/OWN_MOTION_ACK_PACKET_2026-11-05.md; docs/design/previews/motion-slot-frame-v2.html; docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md
  - notes: TODO: packet готов 2026-11-05; ждём YES/NO владельца. Не DONE.
- ✅ **V01** [DESIGN, FULL] Атлас экранов и карта переходов созданы  <br/>status=`DONE`; evidence: docs/design/SCREEN_REFERENCE_ATLAS.md; docs/design/SCREEN_FLOW_MAP.md
- ✅ **V02** [DESIGN, FULL] Визуальное направление и черновик motion сформулированы  <br/>status=`DONE`; evidence: docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md
- ✅ **V03** [DESIGN, FULL] Владелец явно утвердил дизайн ключевых путей  <br/>status=`DONE`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; OWN-DESIGN-ACK
  - notes: Закрыто через OWN-DESIGN-ACK 2026-11-05 (DRAFT pack).
- 🔄 **V04** [DESIGN, FULL] В дизайн-проекте завершены desktop/mobile макеты и состояния ключевых путей  <br/>status=`IN PROGRESS`; evidence: docs/design/V04_KEY_PATH_STATE_MATRIX_DRAFT_2026-11-03.md; docs/design/previews/index.html; docs/design/previews/home-states.html; docs/design/previews/search-states.html; docs/design/previews/profile-states.html; docs/design/previews/event-studio-states.html; docs/design/previews/control-room-states.html; docs/design/previews/deal-hold-forbidden.html; docs/design/previews/cabinet-empty-error.html; docs/design/previews/auth-login-recover.html; docs/design/V04_WIREFRAME_HOME_DEAL_STATES_DRAFT_2026-11-03.md; docs/design/V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_DRAFT_2026-11-03.md; docs/design/V04_WIREFRAME_PROFILE_ARTIST_VENUE_DRAFT_2026-11-05.md; docs/design/V04_WIREFRAME_CABINET_EMPTY_ERROR_DRAFT_2026-11-05.md; docs/design/V04_WIREFRAME_SEARCH_AUTH_DRAFT_2026-11-05.md; OWN-DESIGN-ACK 2026-11-05; docs/design/V04_FIGMA_HANDOFF_2026-11-05.md; docs/design/previews/motion-slot-frame-v2.html
  - notes: IN PROGRESS: agent DRAFT+Figma handoff COMPLETE. НЕ DONE — нужен pixel Figma pack владельца.
- ⛔ **V05** [DESIGN, FULL] Утверждённый дизайн точно перенесён в работающий web  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: V04
- ⛔ **V06** [DESIGN, FULL] Motion утверждён, права на ассеты проверены и интеграция выполнена  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-MOTION-ACK
- 🔄 **V07** [DESIGN, FULL] Web принят по адаптивности, доступности и скорости  <br/>status=`IN PROGRESS`; evidence: apps/web/e2e/cabinet-a11y.spec.ts (390 + keyboard/reduced-motion); apps/web/e2e/responsive-viewports.spec.ts (viewports + unified keyboard + login + artist/compare/legal); docs/ops/V07_LOCAL_PERF_SMOKE_2026-11-03.json; docs/ops/V07_LIGHTHOUSE_LOCAL_SUMMARY_2026-11-03.json (search perf95/a11y100 @390); fix(support) 9010ef1 busyRef + durable reply assert; docs/ops/V07_RESPONSIVE_A11Y_PROGRESS_2026-11-03.md; local playwright 2026-11-05: artist@390/1440 + compare@390 + legal@320 PASS; local playwright 2026-11-05: faq/for-artists/support@390 PASS; local playwright 2026-11-05c: faq/for-artists/support/privacy@390 PASS; local playwright 2026-11-05d: assemble/briefs/investor@390 PASS; local playwright 2026-11-05e: performer services/calendar/messages @390 PASS; local playwright 2026-11-05f: venue halls/requests/calendar + customer messages/favorites @390 PASS; local playwright 2026-11-05f: login recover + control room event @390 PASS; local playwright 2026-11-05g: saved-searches + motion preview @390 PASS; docs/ops/OWN_MOTION_ACK_PACKET_2026-11-05.md; local playwright 2026-11-05h: venue stats + /profile @390 PASS
  - notes: IN PROGRESS: + venue stats + profile @390. НЕ DONE без OWN-MOTION-ACK/D06 и V08 staging.
- ⛔ **V08** [DESIGN, FULL] Визуальный и функциональный путь подтверждён browser E2E на staging  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST, V05

### 14. Безопасность и тестирование

- ✅ **O04** [FULL, INFRA] Точный кандидат имеет зелёный полный CI/security gate  <br/>status=`DONE`; evidence: PR #20 bb61e998
- ✅ **P08** [FULL, INFRA] Полный CI на точном кандидате (FULL)  <br/>status=`DONE`; evidence: PR #20
- ✅ **S01** [FULL] Объектные права и вложения — локальные отрицательные тесты  <br/>status=`DONE`; evidence: test_authz_regressions.py
- ✅ **S04** [FULL] Админский step-up для claim и лимиты iCal локально  <br/>status=`DONE`; evidence: SECURITY_SCAN_2026-10-02.md
- ✅ **S05** [FULL, MVP] Публичные исследования, busy-слоты и фото без прав закрыты  <br/>status=`DONE`; evidence: PUBLIC_CATALOG_PRIVACY_2026-10-02.md
- ⛔ **S07** [FULL] Межорганизационный staging и реальный AV/retention  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ✅ **SEC-01** [MVP, FULL, INFRA] Secret exposure gate source/build/deploy-payload  <br/>status=`DONE`; evidence: scripts/check_secret_exposure.py; SECRET_EXPOSURE_GATE.md
- ✅ **SEC-02** [MVP, FULL] R19/security review V0 hold expire без CRITICAL/HIGH  <br/>status=`DONE`; evidence: docs/ops/evidence/2026-11-02-v0-safe-hold-expire.md
- ✅ **SEC-03** [MVP, FULL] Security review V2 artist supply PASS  <br/>status=`DONE`; evidence: docs/ops/evidence/2026-11-02-v2-artist-profile-services.md
- ✅ **SEC-04** [MVP, FULL] Security review V3 calendar PASS  <br/>status=`DONE`; evidence: docs/ops/evidence/2026-11-02-v3-calendar-requests.md
- ✅ **SEC-05** [MVP, FULL] Полный backend pytest suite зелёный на feature SHA с PG DSN  <br/>status=`DONE`; evidence: 860 PASS after schema fix on V0 worktree
  - notes: На fix/v0-safe-hold-expire; не merged
- ✅ **T06** [MVP, FULL] Объектные права, публичные данные и вложения защищены локально  <br/>status=`DONE`; evidence: apps/api/tests/test_authz_regressions.py; S05 evidence
- ✅ **T08** [MVP, FULL, INFRA] Полный API/web/browser/security CI зелёный на точном SHA  <br/>status=`DONE`; evidence: PR #20 bb61e998 CI run 38480746776
- ⛔ **T11** [MVP, FULL] Межорганизационный staging, AV и retention проверены  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST

### 15. Staging, production и релиз

- ⛔ **O05** [FULL, INFRA] Миграция и восстановление выбранной БД доказаны на staging  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **O06** [FULL, INFRA] Реальные nginx/systemd/cron/оповещения проверены  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **O07** [FULL] Авторизованная сделка, роли и деньги пройдены на staging  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **O08** [FULL, INFRA] Production выпущен с rollback evidence и live E2E  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-PROD-GO, O05, O06, O07
- ⛔ **O09** [FULL] Реальный concierge pilot и supply приняты по метрикам  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: O08, OWN-PILOT
- ✅ **OWN-GIT-INTEGRATION-GO** [MVP, FULL, INFRA] Owner GO на merge feature → delivery/live canonical (не production)  <br/>status=`DONE`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; https://github.com/yaacab/booker/pull/28; PR #28 merge 3f52b582309fe95d23a6b402870c7739f319270b
  - notes: Merged PR #28 → master. Production deploy не входил.
- ⬜ **OWN-PILOT** [FULL] Реальный founding supply/demand pilot согласован  <br/>status=`TODO`; evidence: —
- ⬜ **OWN-PROD-GO** [FULL, INFRA] Отдельное разрешение владельца на production  <br/>status=`TODO`; evidence: F1 NO-GO
  - notes: Только production deploy/live. Не блокирует staging host и не блокирует merge в delivery/live canonical.
- ⬜ **OWN-SMTP** [MVP, FULL] Owner предоставил рабочий SMTP для staging/prod notifications  <br/>status=`TODO`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; docs/ops/SECRETS_INTAKE_OAUTH_SMTP_2026-11-05.md
  - notes: GO на предоставление есть; SMTP значений нет. Intake doc.
- ✅ **OWN-STAGING-GO** [MVP, FULL, INFRA] Owner GO на staging host/DNS/доступ (не production)  <br/>status=`DONE`; evidence: docs/ops/OWNER_GO_EXECUTION_2026-11-05.md; docs/ops/STAGING_PROVISION_PLAYBOOK.md; dig staging.bukergo.ru empty 2026-11-05
  - notes: Owner GO записан. Хост/DNS ещё нет (NXDOMAIN). Не использовать prod 5.45.112.180. Дальше REL-STAGING-HOST после IP+SSH+DNS.
- ✅ **OWN1** [INFRA] Owner packet A/B/C записан; ждать Infrastructure C GO  <br/>status=`DONE`; evidence: docs/ops/FINAL_DELIVERY_HANDOFF.md
  - notes: Packet A/B/C записан. Это не staging GO и не production GO. Дальше: OWN-STAGING-GO / OWN-GIT-INTEGRATION-GO / OWN-PROD-GO раздельно.
- ⛔ **P06** [FULL] Мобильный путь всех ролей пройден на staging (полный запуск)  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **REL-SMTP** [MVP, FULL] Реальная SMTP доставка для recovery/security notifications  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-SMTP
- ⛔ **REL-STAGING** [MVP, FULL, INFRA] Staging окружение доступно для измерений и E2E  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
  - notes: Не путать с OWN-PROD-GO. Staging unreachable (2026-11-03); после host GO проверить health/E2E.
- ⬜ **REL-STAGING-HOST** [MVP, FULL, INFRA] Owner GO на Infrastructure C / remote staging host  <br/>status=`TODO`; evidence: docs/ops/STAGING_HOST_INTAKE_2026-11-05.md; OWN-STAGING-GO 2026-11-05
  - notes: TODO: intake готов; ждём VPS IP/SSH/DNS. Prod IP запрещён.
- ⛔ **T10** [MVP, FULL, INFRA] Миграции и DB+uploads restore проверены на staging  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **T12** [MVP, FULL] Мобильный путь всех ролей пройден на staging с тестовыми данными  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST
- ⛔ **T13** [MVP, FULL, INFRA] Staging nginx/systemd/мониторинг и аварийное восстановление проверены  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: REL-STAGING-HOST

### 16. Документация и юридические требования

- ✅ **DOC-01** [MVP, FULL, INFRA] Единый tasks.json + автопересчёт PROJECT_CHECKLIST  <br/>status=`DONE`; evidence: docs/progress/tasks.json; scripts/progress_recalc.py; docs/PROJECT_CHECKLIST.md; docs/PROJECT_PROGRESS.md AUTO block
  - notes: Task-count formula; historical 59/56/15 preserved separately
- ✅ **LEG-01** [FULL, MVP] CONTRACT.md как продуктовый канон; Artist vNext DRAFT  <br/>status=`DONE`; evidence: docs/product/CONTRACT.md; G1 D01 ACK
- ✅ **LEG-02** [MVP, FULL] ADR-HOLD-001 atomic expire  <br/>status=`DONE`; evidence: docs/adr/ADR-HOLD-001-atomic-expire.md
- ⬜ **LEG-03** [FULL] Хостинг 152-ФЗ / уведомление РКН  <br/>status=`TODO`; evidence: HOSTING_152FZ.md
- ⛔ **LEG-04** [FULL] Оферта проверена юристом (U5)  <br/>status=`BLOCKED`; evidence: docs/legal/
  - blocked_by: OWN-LEGAL-GO
- ✅ **M02** [FULL] Черновой legal pack и consent ledger локально  <br/>status=`DONE`; evidence: LEGAL_CONSENT_LEDGER_2026-10-02.md
- ⛔ **M06** [FULL] Оператор, договоры, простая ЭП и документы утверждены и опубликованы  <br/>status=`BLOCKED`; evidence: —
  - blocked_by: OWN-LEGAL-GO
- ⬜ **OWN-LEGAL-GO** [FULL] Юрист/бухгалтер/реквизиты: legal publish GO  <br/>status=`TODO`; evidence: —
- ✅ **S02** [FULL] Журнал согласий и data-subject workflow локально  <br/>status=`DONE`; evidence: LEGAL_CONSENT_LEDGER_2026-10-02.md

## Правило обновления

1. Меняйте только `docs/progress/tasks.json`.
2. DONE только с evidence (код/тесты/конфиг/документ).
3. Изменение scope — запись в `scope_change_log` с причиной.
4. `python3 scripts/progress_recalc.py`
