# Spec v3 — Delivery Gap Analysis

Источник: [Buker_Cursor_Complete_Spec_v3_2026-09-06.md](specs/Buker_Cursor_Complete_Spec_v3_2026-09-06.md)

SHA аудита: `c90d091` · ветка `feat/master-plan-execution` · PR #14 OPEN

Обновлено: 2026-09-06

Цель: **G2 RC** (без merge/prod без OK). G1/G2 **нельзя** при открытых A/B. E25 = «ожидает G3» до разрешённого deploy.

Легенда Exists: `yes` / `partial` / `no`. Deployed = факт на bukergo.ru.

| ID | Требование | Exists | Tested | Deployed | Gap | Priority | Deps | Evidence |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| A-NAV-HOME | Главная: артист/площадка + дата + поиск | partial | partial | yes | нет dual toggle на первом экране | P0 | — | `app/page.tsx` |
| A-SEARCH-ART | Фильтры спец/дата/формат/выезд/бюджет | partial | partial | yes | нет format/travel/budget | P0 | API | `CatalogFilters`, `/catalog/search` |
| A-SEARCH-VEN | Залы, вместимость/рассадка, оборудование, карта | partial | partial | yes | фильтры зала/карта | P0 | API | `venues/[id]` |
| A-E03 | Синтетический календарь ≠ «свободен» | yes | yes | yes | — | P0 | — | open_data chips |
| A-VITRINE | Публичные витрины + SEO | partial | no | yes | generateMetadata/sitemap профилей | P0 | — | artists/venues pages |
| A-ONBOARD | Onboarding 3 ролей | partial | no | yes | чеклист недостающего | P0 | — | login/register |
| A-CAB-CUST | Кабинет заказчика (сценарии) | partial | partial | yes | подразделы URL | P0 | nav | `cabinet/customer` |
| A-CAB-PERF | Кабинет артиста (сценарии) | partial | partial | yes | Calendar=Requests один href | P0 | W0 | `cabinet/performer` |
| A-CAB-VEN | Кабинет площадки (сценарии) | partial | partial | yes | URL залов/календаря | P0 | W0 | `cabinet/venue` |
| A-AUTHZ | Чужой org/deal/file запрещён | yes | yes | yes | держать regression | P0 | — | authz tests |
| A-HOLD | Double-book запрещён | yes | yes | yes | — | P0 | — | hold race |
| A-DEAL | OfferVersion + Deal Room | yes | yes | yes | — | P0 | — | deals |
| A-PAY-EXT | External + admin confirm (не «онлайн») | yes | partial | yes | отдельные e2e external | P0 | — | payments/external |
| A-PAY-STUB | Stub = только внутренняя логика | yes | yes | n/a | не путать с провайдером | P0 | — | stub tests |
| A-MSG | Сообщения | yes | partial | yes | нет общего inbox | P1 | — | deal chat |
| A-NOTIF | Центр уведомлений | partial | partial | yes | email smtp optional | P1 | EMAIL | SiteChrome |
| A-RECOVER | Password recover | yes | partial | yes | E2E | P1 | — | identity |
| A-BACKUP | Restore DB+files | partial | yes DB | yes | доказать files | P1 | — | RESTORE_DRILL |
| A-MOBILE | ≤5 tabs + org switch | partial | no | yes | tabs → один cabinet | P0 | W0 | SiteChrome |
| B-FAV | Избранное | no | no | no | модель+API+UI | P1 | W3 | — |
| B-COMPARE | Сравнение | no | no | no | — | P1 | W3 | — |
| B-SHARE | Совместные подборки + отзыв | no | no | no | — | P1 | W3 | — |
| B-SAVED | Saved search + consent notify | no | no | no | — | P1 | W3 | — |
| B-BRIEF | Публичные брифы + отклики | no | no | no | marketplace | P1 | W3 | — |
| B-PROMO | Share/QR/supply funnel | no | no | no | organic | P1 | W3 | — |
| B-MULTI-HALL | Атомарный набор залов | no | no | no | E10 | P1 | W2 | — |
| B-REVIEW | Отзывы после Completed | no | no | no | не после Confirmed | P1 | W4 | — |
| B-CLAIM | Claim площадки | no | no | no | без Completed | P1 | W4 | — |
| B-SUPPORT | Жалобы/поддержка | partial | no | partial | очередь | P1 | W4 | — |
| C-LIVE | Live payment | no | no | no | OWNER partner | C | U5 | live.py |
| C-MAP | Карта | no | no | no | OWNER key | C | MAP | — |
| C-SMS | SMS/push | no | no | no | OWNER | C | SMS | — |
| W0-FLAG | query→env→default OFF | partial | no | yes ON | env игнор; default сейчас ON | P0 | W0 | features.ts |
| W0-CI | CI на SHA ветки + PR e2e | partial | yes old | n/a | push на main; e2e nightly | P0 | W0 | ci.yml |
| E25 | Prod smoke | — | — | — | ожидает G3 | G3 | owner OK | — |

## Уточнения

- Query `?event_studio_map_v1=0` = только URL, не глобальный откат.
- Stub-тесты ≠ работоспособность провайдера; external — отдельная приёмка; provider webhook/refund — ждут live+sandbox.
- CI доказательство только для checks на SHA кандидата / PR.
