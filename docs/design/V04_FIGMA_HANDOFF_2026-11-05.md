# V04 — Figma handoff (agent → owner)

**Дата:** 2026-11-05  
**Статус:** handoff. Agent wireframe/preview pack **закрыт**. Этот файл — чеклист pixel Figma для `V04 DONE`.  
**Не делает:** перенос в `apps/web` (`V05`/`D03`), motion ACK, staging.

## Источник правды для кадров

| # | Путь | Static preview | Wireframe |
|---|---|---|---|
| 1 | Home | `previews/home-states.html` | `V04_WIREFRAME_HOME_DEAL_STATES_DRAFT_2026-11-03.md` |
| 2 | Search | `previews/search-states.html` | `V04_WIREFRAME_SEARCH_AUTH_DRAFT_2026-11-05.md` |
| 3 | Profile artist/venue | `previews/profile-states.html` | `V04_WIREFRAME_PROFILE_ARTIST_VENUE_DRAFT_2026-11-05.md` |
| 4 | Event Studio 2–5 | `previews/event-studio-states.html` | `V04_WIREFRAME_EVENT_STUDIO_STEPS_2_5_DRAFT_2026-11-03.md` |
| 5 | Control Room | `previews/control-room-states.html` | (в Event Studio DRAFT) |
| 6 | Deal hold/forbidden | `previews/deal-hold-forbidden.html` | Home/Deal DRAFT |
| 7 | Cabinets E/R | `previews/cabinet-empty-error.html` | `V04_WIREFRAME_CABINET_EMPTY_ERROR_DRAFT_2026-11-05.md` |
| 8 | Auth login/recover | `previews/auth-login-recover.html` | Search/Auth DRAFT |
| 9 | Artist vNext 1/4/6/9 | `previews/artist-vnext-storyboards.html` | `ARTIST_VNEXT_*` + `ART07_ROUTE_AUDIT_*` |

Индекс: `previews/index.html` → локально `/design-previews/`.

## Обязательный Figma pack (закрывает V04)

Для **каждого** пункта: desktop **1440** + mobile **390** (search ещё **768/320**). Состояния минимум: Default / Loading / Empty / Error; где указано — Forbidden / Conflict / Focus.

1. Home — D L E R M  
2. Catalog/search — D L E R Conflict @1440/768/390/320  
3. Artist profile + Venue profile — D L E R F  
4. Event Studio steps 1–5 — D + L/E/R  
5. Control Room — Empty / Waiting / Error  
6. Deal overview + hold-expired + forbidden  
7. Cabinets customer / performer / venue — Empty / Error (Loading/Forbidden желательно)  
8. Auth login + recover — D R F @390  
9. Node ids страниц → таблица `FIGMA_DETAIL_PROGRESS` (file key + node id на кадр)

Язык визуала: cream/gold «рамка слота» как в static preview (`_tokens.css`). Не смешивать с THE AIV.

## Вне пакета

- Live payment / payout UI.  
- Identity redesign (`AUTH-04`).  
- Motion integration (`OWN-MOTION-ACK` отдельно).

## Критерий приёмки V04 DONE

Владелец подтверждает: полный pixel pack по списку выше лежит в дизайн-проекте, node ids записаны, расхождений с DRAFT IA/`OWN-DESIGN-ACK` нет. После этого агент может стартовать `V05`/`D03` перенос.
