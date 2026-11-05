# V04 — матрица desktop/mobile состояний ключевых путей (DRAFT)

**Статус:** DRAFT pack агента **закрыт 2026-11-05**. Не pixel Figma. Не перенос в рабочий web. V04 registry **не DONE** до полного Figma pack.  
**Контракт:** `docs/product/CONTRACT.md` без изменений. Цены/деньги — только API.  
**Студия preview:** `docs/design/previews/index.html` → `/design-previews/` locally.

## Правило кадров

| Код | Состояние | Смысл |
|---|---|---|
| D | Default | Успешные данные / основной путь |
| L | Loading | Скелетон без потери фильтров/прогресса |
| E | Empty | Честное пусто + одно следующее действие |
| R | Error | Повтор; chrome/фильтры не стираются |
| F | Forbidden / Signed-out | Без утечки чужих данных |
| M | Reduced motion | Рамка слота статична |

## Покрытие DRAFT (wireframe + static preview)

| Путь | Wireframe doc | Preview HTML | Pixel Figma |
|---|---|---|---|
| 01 Home L/E/R/M | `V04_WIREFRAME_HOME_DEAL_STATES_*` | `home-states.html` | ○ |
| 02 Search L/E/R/Conflict | `V04_WIREFRAME_SEARCH_AUTH_*` | `search-states.html` | ○ |
| 03 Event Studio 2–5 | `V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_*` | `event-studio-states.html` | ○ |
| 09 Control Room | в Event Studio DRAFT | `control-room-states.html` | ○ |
| Profile artist/venue | `V04_WIREFRAME_PROFILE_ARTIST_VENUE_*` | `profile-states.html` | ○ |
| Deal hold/forbidden | Home/Deal DRAFT | `deal-hold-forbidden.html` | ○ |
| Cabinets E/R/L/F | `V04_WIREFRAME_CABINET_EMPTY_ERROR_*` | `cabinet-empty-error.html` | ○ |
| Auth login/recover | `V04_WIREFRAME_SEARCH_AUTH_*` | `auth-login-recover.html` | ○ |

Индекс: `previews/index.html`.

## Целевой пакет «макеты завершены» = pixel Figma

Агентский wireframe/preview закрыт. Для **V04 DONE** владельцу в Figma:

1. Home D/L/E/R/M @1440+390  
2. Catalog/search D/L/E/R/Conflict @1440/768/390/320  
3. Artist + Venue profile D/L/E/R/F @1440+390  
4. Event Studio 1–5 D + L/E/R @1440+390  
5. Deal overview + hold-expired + forbidden @1440+390  
6. Cabinets (все роли) E/R минимум @1440+390  
7. Auth login/recover D/R/F @390  
8. Node ids → `FIGMA_DETAIL_PROGRESS`

Платежные live-кадры вне пакета.

## Связь с web

Перенос = `V05`/`D03` после pixel + действующего ACK. Этот пакет web runtime не меняет.

## Следующий шаг (не агентский DRAFT)

Pixel Figma по чеклисту `V04_FIGMA_HANDOFF_2026-11-05.md` → оценка V04 DONE. Motion — `OWN_MOTION_ACK_PACKET_2026-11-05.md`. Staging/V07 formal — отдельно.
