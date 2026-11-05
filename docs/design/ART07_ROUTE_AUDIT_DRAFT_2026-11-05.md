# ART-07 — route audit performer IA (DRAFT)

**Статус:** agent DRAFT pack закрыт 2026-11-05. Не pixel Figma. Не перенос канона в `apps/web`.  
**Связь:** `docs/design/ARTIST_VNEXT_STORYBOARD_DRAFT_2026-11-03.md`, preview `previews/artist-vnext-storyboards.html`.  
**ACK:** `OWN-DESIGN-ACK` 05.11.2026 закрыл DRAFT IA pack; formal ART-07 DONE = pixel + web transfer (`V04`/`V05`).

## Фактические маршруты vs 10 сторибордов

| # | Сториборд | Route(ы) сейчас | UI якорь | Gap для переноса |
|---|---|---|---|---|
| 1 | Первый визит | `/cabinet/performer` | `PerformerOnboardingWidget`, `ProfileCompletenessWidget` | empty checklist copy выровнять с DRAFT 3 пункта |
| 2 | Витрина | `/cabinet/performer/services` + home `#supply-settings` | `ServicesWidget`, `PortfolioRiderWidget`, `PublicationWidget` | media-rights checkbox UI уже есть; draft watermark — отдельный visual |
| 3 | Календарь слотов | `/cabinet/performer/calendar` | `CalendarOverviewWidget`, `OpenSlotsWidget`, `CalendarConflictsWidget` | held chip → deal CTA без «оплаты» — ок; conflict inline — проверить copy |
| 4 | Входящая заявка | `/cabinet/performer/requests` | `data-testid=performer-requests-inbox` | комиссия hint «посчитает сервер» — сверить label суммы |
| 5 | Deal Room supply | `/deals/{id}` | `data-testid=deal-room-accents` | terms version banner уже в Deal Room; forbidden org — API 403 |
| 6 | Публичный профиль | `/artists/{id}` | catalog → profile e2e | sticky CTA @390 — visual; busy chip — слоты |
| 7 | Draft vs published | home + `PublicationWidget` | `performer-publication-status` / toggle | banner «черновик» на public preview — gap |
| 8 | Сообщения до оффера | `/cabinet/performer/messages` | `MessagesHubClient` h1 «Сообщения» | тот же thread id после offer — API; UI не плодит новый чат |
| 9 | Мобильный ответ | `/cabinet/performer/requests` @390 | keyboard chain e2e unified | covered V07 local |
| 10 | Ошибка и отказ | requests + deal | offer error toast / decline | decline reason select — проверить наличие |

## Автономно закрыто этим срезом

1. Таблица маршрутов выше.  
2. Static preview кадров 1 / 4 / 6 / 9 (+ appendix 2/3/5/7/8/10) в `artist-vnext-storyboards.html`.  
3. Индекс `/design-previews/` ссылается на ART-07 pack.  
4. V07 overflow/landmark smoke на `services` / `calendar` / `messages` @390.

## Не закрывает ART-07 DONE

- Pixel Figma frames 1–10.  
- Перенос visual language / sticky CTA / draft banner в runtime (`V05`/`D03`).  
- Identity redesign (`AUTH-04`).
