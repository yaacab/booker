# Букер — сводная приёмка коммерческого этапа

Дата: 2026-09-15. Ветка: `feat/prelaunch-commercial-v1`.
Статус: **технический объём разделов 0–35 принят**. Внешние действия владельца перечислены ниже; production не выпускался.

## Что было до изменений

Проверенная база `834fb22` содержит `origin/master ca20ac2`, действующий дизайн,
RBAC, каталог/календари, OfferVersion/quote_id/ack/hold, Deal Room, договор,
booking adapter, favorites/compare/shared shortlist/public briefs, отзывы и поддержку.
Commerce plans/orders/campaigns, Growth, server matching/compatibility/readiness/budget,
Business и полноценная коммерческая приёмка отсутствовали. Старый GAP-анализ
2026-09-06 не отражал уже существовавшие функции. Подробная исходная карта и
хронология доказательств: [PRELAUNCH_V1.md](PRELAUNCH_V1.md).

## Приёмка разделов задания

Ссылки на API tests относятся к `apps/api/tests`, E2E — к `apps/web/e2e`.
UI/API/DB/auth/audit и состояния описаны в соответствующих главах журнала;
отсутствие внешнего PSP не подменяется локальным успехом.

### 0. Ограничения и исходная карта

Отдельный worktree и feat/prelaunch-commercial-v1 от 834fb22, содержащего проверенный origin/master ca20ac2. Merge, deploy, DNS, real PSP и массовые отправки не выполнялись. Незакоммиченный исходный workspace сохранён.

Доказательства: PRELAUNCH_V1.md.

### 1–4, 6. Контракт, commerce, provider и неизменяемая цена

Contract v3, версионируемые планы/продукты, Subscription/BillingOrder/PromotionCampaign, disabled/stub и регистрация выбранного адаптера. Durable checkout, signed settlement, recurring periods. Fees и entitlements только серверные; OfferVersion защищён DB trigger.

Доказательства: test_commerce.py, test_subscription_cycles.py, test_checkout_receipts.py, test_payment_activation.py.

### 5, 8. Тарифы и коммерческий кабинет

/pricing разделяет артиста, площадку и организатора; API возвращает цены, годовую экономию и комиссии. Supply growth cabinet показывает тариф, renew/change, заказы, promotion и credits. Ошибки и неопределённый checkout имеют явный retry.

Доказательства: commercial.spec.ts, subscription-cycles.spec.ts.

### 7. Продвижение

Строгие город/категория/дата/фильтры до sponsored insertion, максимум floor(N/5), без соседних sponsored, маркировка Продвижение. Credits и attribution привязаны к серверным фактам. Занятые, чужие и неподтверждённые к продвижению профили исключены.

Доказательства: test_paid_promotion.py, promotions.spec.ts.

### 9. Growth

Наблюдаемый funnel от показа до Completed, периоды по entitlement, реальные гонорары/response time/свободные даты, явные причины потери. Benchmark только Premium и cohort ≥10, без показателей конкретных конкурентов.

Доказательства: test_growth.py, growth.spec.ts.

### 10. Opportunities

Публичный brief с согласием заказчика; объяснимый match, manual response, Free доступ к самим заказам. Pro/Premium saved filters и consent alerts. Никаких auto-offers.

Доказательства: test_opportunities.py, opportunities.spec.ts.

### 11. EPK

Версионируемая витрина с медиа, программой/составом/форматом, райдером, географией и тарифами; права на медиа, Free профиль, фактические trust metrics, request/favorite/compare/share.

Доказательства: test_presentation.py, artist-presentation.spec.ts.

### 12. Подбор состава

Три серверных варианта, ориентиры опубликованных тарифов, явная оговорка об отсутствии quote. EventPlan с revision/context, ручные замены и отдельная идемпотентная отправка заявок.

Доказательства: test_matching.py, test_event_planning.py, smart-matching.spec.ts, studio-estimate.spec.ts.

### 13. Compare V2

Артисты и залы: дата, ориентир, состав/оборудование, факты отзывов/сделок/ответов, техническая совместимость. Добавление в предварительный EventPlan не создаёт бронь.

Доказательства: test_comparison.py, compare-v2.spec.ts.

### 14. Совместимость

Event ↔ artist ↔ venue, полное окно с буферами, вместимость, сцена, звук, микрофоны, DJ/power и недостающее оборудование. Unknown отличается от incompatible. Версионируемый редактор техники зала.

Доказательства: test_compatibility.py, compatibility.spec.ts.

### 15. Готовность события

Серверные score/checklist/blockers/next_best_action; настоящий hold/ack/contracts/payment. Negotiation не закрывает роль, поздний capture не обещает дату. Кабинет ведёт к следующему действию.

Доказательства: test_event_readiness.py, event-readiness.spec.ts.

### 16. Бюджет

budget-summary отделяет подтверждённые обязательства и ориентиры, не складывает альтернативных кандидатов, различает unknown/zero/partial, учитывает непокрытые роли и перерасход.

Доказательства: test_event_budget.py, event-budget.spec.ts.

### 17. Совместный выбор

Scoped expiring/revocable guest capability, vote/favorite/reject/comment, rate limit и audit. Нет доступа к аккаунту, контактам и подписанию сделки.

Доказательства: test_collaboration.py, collaboration.spec.ts.

### 18. Повтор

Completed → чистый Draft, новые роли и optional preferred participants. Никаких старых quote/hold/payment/signature/availability; новый интервал проверяется заново.

Доказательства: test_event_repeat.py, event-repeat.spec.ts.

### 19. Замена

Ручной подбор действительно доступных кандидатов после отмены участника, проверка актуальности даты при запросе. Нет страхования и гарантии наличия замены.

Доказательства: test_replacement_candidates.py, event-replacement.spec.ts.

### 20. Business

Шаблоны, clone/repeat, внутренние заметки, история поставщиков, аналитика событий, ZIP документов, support priority. Команда через прежний Organization/TeamMember RBAC и серверные лимиты мест.

Доказательства: test_business_workflows.py, test_business_reporting.py, test_team.py, test_support_priority.py; business-workflows.spec.ts, team.spec.ts, support-priority.spec.ts.

### 21. Уведомления

Все десять требуемых событий имеют in-app coverage: request/offer, сроки offer/hold, opportunity match, сроки promotion/subscription, payment required, event blocker и replacement. Адресная лента, dedupe/read/deep links. Транспорты отключаемы, SMTP outbox после commit, consent для marketing.

Доказательства: test_notifications.py, test_inbox.py, test_lifecycle_notifications.py, test_outbox_delivery.py, test_payment_guards.py.

### 22. Админка

Версии цен с причиной/audit, grant/revoke с CAS и защитой provider-linked подписок; состояния campaigns; GMV/accrued fees и captured/refunded отдельно от stub/projected. Сверка booking payment и four-eyes refunds.

Доказательства: test_admin_commercial.py, test_commercial_revenue.py, test_payment_reconciliation.py, test_refunds.py; admin-commercial.spec.ts, admin-refunds.spec.ts, payment-reconciliation.spec.ts.

### 23. Аналитика

ANALYTICS.md описывает требуемую taxonomy и дополнительные transition events. Public discovery дедуплицирован, profile/favorite/request/offer/hold/booking берутся из соответствующих фактов; админские acquisition/supply/revenue/subscription/promotion агрегаты.

Доказательства: test_analytics.py, test_analytics_entity.py, test_growth.py, test_commercial_revenue.py.

### 24. SEO

Metadata/canonical/OG публичных профилей, пагинируемый sitemap без зависимости от search/calendar, SSR город/категория только при достаточном содержимом. Фактический ItemList, no thin pages, HTML без JS.

Доказательства: test_seo.py, seo-catalog.spec.ts.

### 25. Доверие

Отзывы только Completed и от участника, реальные completed/response time/verified/reviews. Нет платной верификации, отзывов, скрытия негатива или изменения trust метрик подпиской.

Доказательства: test_reviews.py, test_trust_outbox.py, test_presentation.py, test_growth.py.

### 26. Безопасность

Object/org/role auth, rate limits, дедупликация команд и audit по смыслу операции. Cross-org billing/profile/analytics запрещены; server quote snapshots, signed raw webhooks, no secret payload logs, guest/team capabilities scoped и hashed.

Доказательства: test_authz_regressions.py, test_idor_events.py, test_totp_security.py, test_commerce.py, test_paid_promotion.py, test_provider_webhook.py, test_refund_webhook.py.

### 27. UX и адаптивность

Сохранён существующий lime-дизайн. Новые сценарии проверены в браузере на 1440/390, включая keyboard, overflow, loading/error/empty и retry после потери ответа. Суммы и статусы API отображаются русским UI.

Доказательства: 126-test PR suite; отдельные визуальные артефакты и проверки перечислены в PRELAUNCH_V1.md.

### 28. Флаги

COMMERCIAL_PLANS, PAID_PROMOTION, ARTIST_GROWTH, OPPORTUNITIES, SMART_MATCHING, COMPATIBILITY, CUSTOMER_BUSINESS и дополнительные collaboration/repeat flags. Free не исчезает при выключенной коммерции; payment defaults disabled, opt-in false.

Доказательства: config.py, test_commerce.py, test_payment_guards.py, test_payment_activation.py.

### 29–31. Проверки и CI

API, PostgreSQL concurrency, миграции SQLite/PG, TypeScript, build и именованные E2E E-COM/E-GROWTH/E-OPP/E-CUST/E-COLLAB/E-REPEAT/E-REPLACE. CI на PR включает коммерческие сценарии; SQLite CLI устанавливается для backup/restore. Remote Actions не запускались.

Доказательства: Точные результаты ниже и в PRELAUNCH_V1.md.

### 32–33. Документация и передача платежей

COMMERCIAL_MODEL, PRELAUNCH_V1, CONTRACT, ROADMAP, ANALYTICS, LAUNCH_CHECKLIST, DELIVERY_GAP_ANALYSIS, OWNER_INPUTS и PAYMENT_PROVIDER_HANDOFF. Booking/commerce сохраняют собственные state machines; подключение PSP ограничено адаптером, его конфигурацией и внешней приёмкой.

Доказательства: docs/product/*, docs/integrations/PAYMENT_PROVIDER_HANDOFF.md.

### 34–35. Итоговая приёмка и отчёт

Настоящий документ объединяет требования, изменения, API/pages/migrations, проверки, monetization, external inputs и git. Последний полный API-прогон, включая activation gate, PostgreSQL и backup/restore: 604 passed без пропусков.

Доказательства: Текущий полный прогон /tmp/booker-activation-full.log.

## Миграции

Новые миграции относительно 834fb22; текущая head — `a0b1c2d3e4f5`.
Исторические деньги не пересчитываются, дубликаты provider references не исправляются
молча. Порядок определяется Alembic down_revision, а не списком ниже.

- `a0b1c2d3e4f5_subscription_periods.py`
- `a2b3c4d5e6f7_opportunities.py`
- `a4b5c6d7e8f9_notification_inbox.py`
- `b3c4d5e6f7a8_artist_presentation.py`
- `b5c6d7e8f9a0_outbox_claims.py`
- `b9c0d1e2f3a4_repeat_preferences.py`
- `c0d1e2f3a4b5_business_workflows.py`
- `c4d5e6f7a8b9_hall_technical.py`
- `c6d7e8f9a0b1_offer_validity.py`
- `d1e2f3a4b5c6_team_invitations.py`
- `d5e6f7a8b9c0_event_commands.py`
- `d7e8f9a0b1c2_payment_session_receipt.py`
- `d9e0f1a2b3c4_commercial_core.py`
- `e0f1a2b3c4d5_promotion_attribution.py`
- `e2f3a4b5c6d7_support_priority.py`
- `e6f7a8b9c0d1_event_plans.py`
- `e8f9a0b1c2d3_payment_refunds.py`
- `f1a2b3c4d5e6_discovery_signals.py`
- `f3a4b5c6d7e8_support_replies.py`
- `f7a8b9c0d1e2_shortlist_collaboration.py`
- `f9a0b1c2d3e4_payment_event_binding.py`

## API: добавленные и расширенные интерфейсы

### Каталог, тарифы, billing orders, cycles, promotions и коммерческая админка

- `GET /commerce/catalog` — `catalog`.
- `GET /commerce/organizations/{org_id}` — `organization_commerce`.
- `POST /commerce/organizations/{org_id}/orders` — `create_order`.
- `GET /commerce/orders/{order_id}` — `get_order`.
- `POST /commerce/orders/{order_id}/checkout` — `retry_checkout`.
- `POST /commerce/orders/{order_id}/cancel` — `post_cancel_order`.
- `POST /commerce/organizations/{org_id}/subscription/cancel` — `post_cancel_subscription`.
- `POST /commerce/organizations/{org_id}/subscription/change` — `post_change_subscription`.
- `POST /commerce/renewal-webhook` — `renewal_webhook`.
- `POST /commerce/webhook` — `webhook`.
- `POST /commerce/orders/{order_id}/test-complete` — `test_complete`.
- `GET /admin/commerce/catalog` — `admin_catalog`.
- `PUT /admin/commerce/plans/{code}` — `update_plan`.
- `POST /admin/commerce/organizations/{org_id}/grant` — `grant_plan`.
- `POST /commerce/organizations/{org_id}/promotions` — `post_promotion`.
- `GET /commerce/organizations/{org_id}/promotions` — `get_promotions`.
- `POST /commerce/promotions/{campaign_id}/cancel` — `post_cancel_campaign`.
- `POST /commerce/promotion-touches/{touch_id}` — `post_promotion_touch`.
- `PUT /admin/commerce/promotions/{audience}/{code}` — `update_promotion_price`.
- `GET /admin/commerce/organizations` — `commercial_organizations`.
- `POST /admin/commerce/organizations/{org_id}/revoke` — `revoke_plan`.
- `GET /admin/commerce/revenue` — `commercial_revenue`.
- `GET /admin/commerce/campaigns` — `commercial_campaigns`.

### Наблюдаемый funnel, loss reasons и экспорт

- `POST /discovery/signals` — `post_signal`.
- `GET /organizations/{org_id}/growth` — `get_growth`.
- `GET /organizations/{org_id}/growth/export` — `export_growth`.
- `POST /requests/{request_id}/loss-reason` — `post_loss`.

### Подходящие briefs и saved filters

- `GET /organizations/{org_id}/opportunities` — `get_opportunities`.
- `GET /organizations/{org_id}/opportunity-filters` — `get_filters`.
- `POST /organizations/{org_id}/opportunity-filters` — `create_filter`.
- `DELETE /opportunity-filters/{filter_id}` — `delete_filter`.

### Публичная витрина и её версионируемое редактирование

- `GET /artists/{artist_id}/presentation` — `read_presentation`.
- `PUT /artists/{artist_id}/presentation` — `save_presentation`.

### Ориентиры, EventPlan, budget и readiness

- `POST /event-studio/estimate` — `estimate_selection`.
- `GET /events/{event_id}/matching` — `event_matching`.
- `PUT /events/{event_id}/plan` — `save_event_plan`.
- `PATCH /events/{event_id}/planning-context` — `update_planning_context`.
- `GET /events/{event_id}/budget-summary` — `budget_summary`.
- `GET /events/{event_id}/readiness` — `readiness_summary`.
- `GET /orgs/{organization_id}/event-readiness` — `readiness_overview`.

### Сравнение по фактам

- `GET /compare` — `compare_candidates`.

### Совместимость и технические профили залов

- `GET /organizations/{org_id}/technical-halls` — `list_technical_halls`.
- `GET /halls/{hall_id}/technical` — `get_technical`.
- `PUT /halls/{hall_id}/technical` — `put_technical`.
- `POST /compatibility` — `compatibility`.

### Повтор события и preferred participants

- `GET /events/{event_id}/repeat-options` — `repeat_options`.
- `POST /events/{event_id}/repeat` — `repeat_event`.
- `GET /events/{event_id}/repeat-preferences` — `repeat_preferences`.

### Шаблоны, заметки, clone, reports и документы

- `GET /business/organizations/{org_id}/templates` — `list_templates`.
- `POST /business/organizations/{org_id}/templates` — `create_template`.
- `POST /business/templates/{template_id}/archive` — `archive_template`.
- `POST /business/templates/{template_id}/events` — `instantiate_template`.
- `POST /business/events/{event_id}/clone` — `clone_event`.
- `GET /business/events/{event_id}/notes` — `list_notes`.
- `POST /business/events/{event_id}/notes` — `create_note`.
- `PUT /business/notes/{note_id}` — `edit_note`.
- `DELETE /business/notes/{note_id}` — `delete_note`.
- `GET /business/organizations/{org_id}/report` — `business_report`.
- `GET /business/organizations/{org_id}/documents.zip` — `export_documents`.

### Участники команды и приглашения

- `GET /orgs/{org_id}/team` — `get_team`.
- `POST /orgs/{org_id}/team/invitations` — `invite`.
- `POST /orgs/{org_id}/team/invitations/{invite_id}/revoke` — `revoke`.
- `POST /team-invitations/accept` — `accept`.
- `PUT /orgs/{org_id}/team/members/{member_id}` — `edit`.
- `DELETE /orgs/{org_id}/team/members/{member_id}` — `remove`.
- `POST /team-invitations/preview` — `preview`.

### Адресная лента уведомлений

- `GET /notifications` — `notifications`.
- `POST /notifications/{notification_id}/read` — `mark_read`.

### Публичный индекс, профили и наполненные подборки

- `GET /seo/index` — `index`.
- `GET /seo/profiles` — `profiles`.
- `GET /seo/collections/{city_slug}/{category}` — `collection`.

### Запрос и независимое подтверждение возврата

- `GET /admin/refunds` — `list_refunds`.
- `POST /admin/refunds` — `create_refund`.
- `POST /admin/refunds/{refund_id}/approve` — `approve_refund`.
- `POST /admin/refunds/{refund_id}/reject` — `reject_refund`.
- `POST /admin/refunds/{refund_id}/retry` — `retry_refund`.
- `POST /admin/refunds/{refund_id}/refresh` — `refresh_refund`.
- `POST /admin/refunds/{refund_id}/confirm-external` — `confirm_external`.

Booking дополнительно: `POST /payments/provider-webhook`,
`POST /payments/refund-provider-webhook`, `POST /admin/payments/{id}/reconcile`,
расширенный `POST /bookings/{id}/payments`; прежние quotes/ack/hold/contract/cancel
и replacement routes усилены без переноса цены на frontend. Полный API contract —
OpenAPI текущего приложения; вспомогательные функции Python не являются endpoints.

## Страницы

Новые и расширенные страницы относительно базы (включая существующие маршруты):

- `/admin/commerce`.
- `/admin`.
- `/admin/refunds`.
- `/artists/[id]`.
- `/briefs`.
- `/cabinet/customer/business`.
- `/cabinet/performer/growth`.
- `/cabinet/performer/opportunities`.
- `/cabinet/performer/presentation`.
- `/cabinet/venue/growth`.
- `/cabinet/venue/opportunities`.
- `/cabinet/venue/technical`.
- `/catalog/[city]/[category]`.
- `/catalog`.
- `/compare`.
- `/compatibility`.
- `/deals/[id]`.
- `/events/[id]`.
- `/events/new`.
- `/faq`.
- `/notifications`.
- `/pricing`.
- `/profile`.
- `/s/[token]`.
- `/search`.
- `/support`.
- `/team/join`.
- `/team`.
- `/venues/[id]`.

Назначения страниц соответствуют разделам приёмки выше; `/sitemap.xml` и
`/sitemaps/{kind}/{page}.xml` — XML handlers, не пользовательские страницы.

## Monetization

`commerce/fees.py` определяет тариф организации в момент публикации OfferVersion.
Заказчик платит H + round(H×600/10000), исполнитель получает
H − round(H×400|300|200/10000), платформа начисляет сумму двух комиссий.
Округление каждой комиссии: `(H*bps + 5000)//10000`, integer RUB.
Free/Pro/Premium дают 6+4 / 6+3 / 6+2; versioned policy и все денежные результаты
сохраняются в неизменяемом snapshot. Изменение плана не меняет старую цену.
Подписки и promotion — отдельные BillingOrder. Paid устанавливает проверенный
provider event; checkout, manual entitlement и прогноз не являются captured money.

## Проверки: точные результаты

История запусков и команды: [PRELAUNCH_V1.md](PRELAUNCH_V1.md).
Финальная команда из корня worktree:
```bash
PATH=/tmp/booker-sqlite-runtime/extracted/usr/bin:/tmp/booker-prelaunch-tools/bin:$PATH BOOKER_TEST_POSTGRES_URL=postgresql+psycopg://art67@127.0.0.1:55433/postgres BOOKER_DATABASE_URL=sqlite:// BOOKER_ENVIRONMENT=test make test-api
```
**604 passed, 0 skipped, 339.87s**; лог `/tmp/booker-activation-full.log`.
32 проверки регистрации/допуска также прошли отдельно на окончательном коде.
Предыдущие два skip из-за отсутствия SQLite CLI устранены установкой локального
runtime; окончательный прогон включает backup/restore вместе с остальными тестами.
`make lint`, `make web-lint` и `make web-build` прошли; production frontend build
после SEO не менялся. GitHub Actions на remote SHA не запускались.

Общий PR Playwright: 120 passed / 6 failed (126 tests, 5.3m).
Устаревшие selectors/fixtures исправлены: 14 passed / 1 failed на пяти файлах,
затем cross-role 2 passed (21.2s). Все исходно упавшие случаи успешно перепроверены.
Это результаты нескольких запусков, а не один выдуманный зелёный запуск.
Все обязательные E-COM-01…07, E-GROWTH-01, E-OPP-01…02, E-CUST-01…05,
E-COLLAB-01, E-REPEAT-01 и E-REPLACE-01 входят в прошедшие сценарии.

## Внешние действия владельца

1. Выбрать PSP, реализовать его protocol/SDK в подготовленных adapters,
   зарегистрировать factories, проверить merchant/signature/refund/recurring consent
   и пройти реальный sandbox acceptance. Настоящего PSP в репозитории нет.
2. Заполнить реквизиты оператора, получить утверждение юриста и платёжного партнёра.
3. Подготовить production secrets, БД/storage и эксплуатацию в РФ, РКН/152-ФЗ,
   каналы поддержки и мониторинг, выполнить restore на реальной инфраструктуре.
4. Отдельно разрешить и провести production release/smoke, затем acquisition.

Локальные stub и restore fixtures не доказывают факт оплаты, юридическую готовность,
регистрацию РКН или сохранность production storage. Эти шаги явно вынесены владельцем
за пределы задачи; продуктовых auto-offers, AI-споров или платного trust нет.

## Payment handoff и Git

Точные точки: `apps/api/booker_api/payments/adapter.py::register_payment_adapter`
и `apps/api/booker_api/commerce/provider.py::register_commerce_provider`.
Общий допуск: `apps/api/booker_api/payment_activation.py`.
Инструкция: [PAYMENT_PROVIDER_HANDOFF.md](../integrations/PAYMENT_PROVIDER_HANDOFF.md).
Ветка `feat/prelaunch-commercial-v1`; код и допуск адаптера — `5de7da3`,
общая E2E regression — `ef43132`. Итоговый SHA с документацией сообщается после её коммита.
Merge, production deploy и DNS не выполнялись.
