# V04 — матрица desktop/mobile состояний ключевых путей (DRAFT)

**Статус:** DRAFT для дизайн-проекта. Не утверждение владельца. Не разрешение переносить визуальный язык в рабочий web.  
**Контракт:** `docs/product/CONTRACT.md` без изменений. Цены/деньги — только API.  
**База:** `SCREEN_REFERENCE_ATLAS.md`, `SCREEN_FLOW_MAP.md`, `FIGMA_DETAIL_PROGRESS_2026-09-30.md`, `ROUTE_AUDIT_2026-09-30.md`.

## Правило кадров

Для каждого ключевого пути нужны кадры **Desktop 1440** и **Mobile 390** (плюс stress 320 где уже начато) в состояниях:

| Код | Состояние | Смысл |
|---|---|---|
| D | Default | Успешные данные / основной путь |
| L | Loading | Скелетон/spinner без потери фильтров и прогресса |
| E | Empty | Честное пустое + одно следующее действие |
| R | Error | Повтор / альтернатива; фильтры не стираются |
| F | Forbidden / Signed-out | Без утечки чужих данных |
| M | Reduced motion | Без подъёма/параллакса; смысл сохранён |

## Покрытие Figma на 2026-11-03

Источник: `FIGMA_DETAIL_PROGRESS_2026-09-30.md` (`Booker Detail / Motion v1`).

| Путь | 1440 D | 390 D | L/E/R | M | 320 | Остаток для V04 |
|---|---|---|---|---|---|---|
| 01 Home | ✓ | ✓ | ○ | ✓ | ✓ reflow | Loading/Empty/Error home |
| 02 Choice / search space | ✓ Date-District | ✓ | ✓ 1440+390 | ○ | ✓ stress | keyboard/scroll-snap interactive; opaque button fallback |
| 03 Event Studio step 1 | ✓ | ✓ | ○ | storyboard only | ○ | Figma L/E/R/F step 1 |
| 03b Event Studio steps 2–5 | wireframe DRAFT | wireframe DRAFT | wireframe D/L/E/R/Conflict | wireframe M | ○ | pixel Figma + node ids |
| 09 Control Room cards | wireframe DRAFT | wireframe DRAFT | wireframe D/E/R | wireframe M | ○ | pixel Figma |
| Profile artist/venue | wireframe DRAFT | wireframe DRAFT | wireframe D/L/E/R/F | wireframe M | ○ | pixel Figma; см. `V04_WIREFRAME_PROFILE_ARTIST_VENUE_*` |
| Request → Deal Room | wireframe Home/Deal DRAFT | wireframe | hold/forbidden DRAFT | ○ | ○ | overview/chat + hold expiry pixel |
| Cabinets customer/performer/venue | ○ | ○ | ○ | ○ | ○ | home + requests + empty/error |

Итого: wireframe DRAFT расширен (Home/Deal + Event Studio 2–5 + Control Room). Pixel Figma pack не закрыт. V04 **не DONE**.

## Целевой минимальный пакет для «макеты ключевых путей завершены»

Без этого пакета `OWN-DESIGN-ACK` принимать рано:

1. Home — D/L/E/R/M @1440+390  
2. Catalog/search — D/L/E/R/Conflict + API list @1440/768/390/320  
3. Artist + Venue profile — D/L/E/R/F @1440+390  
4. Event Studio — шаги 1–5 D + L/E/R на шаге сохранения @1440+390  
5. Deal Room — overview + terms + hold-expired @1440+390  
6. Cabinet performer requests — D/E/R @1440+390  
7. Auth login/recover — D/R/F @390  

Платежные кадры live **вне** этого пакета до `OWN-LEGAL-GO` / `OWN-PAY-PARTNER`.

## Связь с текущим web (не перенос дизайна)

| Путь | Код route | Заметка DRAFT |
|---|---|---|
| Home | `app/page.tsx` | Scene01 live; reduced-motion CSS есть |
| Search | `app/search/page.tsx` | labels/overflow e2e есть; Figma Choice ≠ pixel parity |
| Artist | `app/artists/[id]` | CONTRACT-канон профиля; vNext IA отдельно |
| Deal | `app/deals/[id]` | accents/tabs; hold UI не путать с confirmed |
| Performer requests | `app/cabinet/performer/requests` | inbox + «Создать предложение» |

Перенос утвержденных кадров в web = задачи `V05`/`D03` после `OWN-DESIGN-ACK`. Этот документ сам по себе web не меняет.

## Следующий автономный шаг (дизайн-проект)

1. Перенести wireframe DRAFT → pixel Figma: Home L/E/R, Event Studio 2–5, Control Room cards, Deal hold/forbidden.  
2. Artist + Venue profile D/L/E/R/F @1440+390.  
3. Cabinet performer requests D/E/R @1440+390.  
Агент без Figma API владельца фиксирует матрицу и gaps; pixel-кадры — в файле Figma владельца.  
Wireframe docs: `V04_WIREFRAME_HOME_DEAL_STATES_*`, `V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_*`.
