# V04 — Artist + Venue public profile wireframe (DRAFT)

**Статус:** DRAFT. Не перенос в `apps/web`. Pixel Figma отдельно.  
**Связь:** матрица `V04_KEY_PATH_STATE_MATRIX_*` строка Profile; ART-07 storyboards 6/7.  
**Цены:** только «из API / ориентир»; не обещать live payout.

## Artist `/artists/{id}`

| Состояние | 1440 | 390 | Copy / правила |
|---|---|---|---|
| D | Gallery + facts + slots week + CTA «Добавить в событие» | Sticky bottom CTA; gallery full-bleed без card-stack | CTA не говорит «забронировано» |
| L | Skeleton gallery + facts | То же | «Загружаем профиль…» |
| E unpublished | Empty main + draft notice только владельцу | То же | Visitor: 404/не найдено без утечки draft |
| R | Banner ошибки API | То же | «Не удалось загрузить. Повторить.» |
| F signed-out CTA | Modal/redirect login?next= | Bottom sheet | Сохранить deep link |
| Busy date | Chip «занято» на слоте | То же | CTA остаётся «добавить в событие», не «оплатить» |
| M | Без autoplay media | Reduced motion gallery | scroll без 3D |

## Venue `/venues/{id}`

| Состояние | 1440 | 390 | Copy / правила |
|---|---|---|---|
| D | Halls list + map/address + capacity + CTA | Vertical halls; map below fold | «Запрос на дату — не бронь» |
| L | Skeleton halls | То же | «Ищем залы…» |
| E no halls | Empty halls | То же | «Залы ещё не опубликованы» |
| R | API fail banner | То же | Повторить; не чистить адрес |
| Needs review | Не в public catalog | — | Admin/investor отдельно; visitor не видит |
| F | login?next=venue | То же | — |
| M | Map static fallback | То же | без параллакса |

## Shared forbidden

- Показывать точный busy другого org  
- «Оплачено» / checkout на профиле  
- Identity redesign / OAuth UI здесь  

## Чеклист Figma владельца

- [ ] Artist D/L/E/R/F/Busy/M @1440+390  
- [ ] Venue D/L/E/R/F/M @1440+390  
- [ ] Node ids → `FIGMA_DETAIL_PROGRESS`  
