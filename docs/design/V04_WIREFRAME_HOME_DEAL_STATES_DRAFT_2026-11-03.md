# V04 — wireframe copy: Home L/E/R + Deal hold/forbidden (DRAFT)

**Статус:** DRAFT. Не pixel-perfect. Не перенос в `apps/web`. Не `OWN-DESIGN-ACK`.  
**Зачем:** закрыть пробелы матрицы V04 без Figma API — готовые тексты/структура кадров для файла владельца.

## A. Home @1440 и @390

| Кадр | Структура (сверху вниз) | Copy (RU) | CTA |
|---|---|---|---|
| D Default | Brand → promise → primary CTA → secondary | «Букер» / «Артисты и площадки для вашего события.» | «Собрать событие», «Открыть каталог» |
| L Loading | Те же якоря; блоки-скелетоны вместо подборок | «Загружаем подборки…» (sr-only ok) | CTA disabled или скрыты до данных |
| E Empty | Promise + честное пусто | «Пока нет опубликованных подборок.» | «Открыть каталог», «Создать заявку» |
| R Error | Promise + ошибка + повтор | «Не удалось загрузить главную. Проверьте сеть.» | «Повторить», «Открыть каталог» |
| M Reduced | Как D без motion tracks | без параллакса/подъёма карточек | те же CTA |

Правила: CTA над сгибом на 390; no-JS fallback уже есть в live (`bk-live-fallback`) — Figma кадр M/E не должен требовать JS.

## B. Deal Room @1440 и @390

| Кадр | Состояние | Что видно | Чего нет |
|---|---|---|---|
| Overview D | Активная версия оффера | статус даты, quote_id, «что дальше» | цена не из макета — «из API» |
| Overview Hold active | Hold действует | таймер/срок hold, стороны ack | held ≠ confirmed |
| Overview Hold expired | Hold истёк | «Слот больше не удерживается» | нельзя CTA «Оплатить»/confirm как будто слот жив |
| Terms D | Активная версия | состав, что включено | принять устаревшую версию нельзя |
| Chat D | Переписка сделки | системные события отдельно | чужие org не светятся |
| F Forbidden | Нет доступа / вышли | «Нет доступа к этой сделке» | без subject/сумм/имён сторон |

## C. Связь с live (только сверка, не redesign)

- Home: `components/Scene01LiveHome.tsx` + noscript fallback.  
- Deal: `app/deals/[id]` + `deal-room-accents`; e2e `responsive-viewports` уже бьёт overflow @390.  
- Новые copy из этого файла **не** вшивать в web до `OWN-DESIGN-ACK`.

## D. Готовность к Figma (чеклист владельца)

- [ ] Home L/E/R @1440  
- [ ] Home L/E/R @390  
- [ ] Deal hold-expired @1440+390  
- [ ] Deal forbidden guest @1440+390  

После галочек — обновить `FIGMA_DETAIL_PROGRESS_*.md` node id и вернуться к V04 status.
