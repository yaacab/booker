# V04 — Cabinet empty / error states (DRAFT)

**Статус:** DRAFT. Не перенос в `apps/web`.  
**Preview:** `docs/design/previews/cabinet-empty-error.html`  
**Локальный URL (если Next уже поднят):** `http://127.0.0.1:3000/design-previews/cabinet-empty-error.html`  
**Роли:** customer / performer / venue. Viewports: 1440 + 390.  
**Правила:** цена/комиссия только «из API»; held ≠ confirmed; без Identity redesign.

## Визуальный канон этого пакета

Не invent-new-brand. Токены как у cream / Scene01 / «рамка слота»:

| Токен | Значение | Зачем |
|---|---|---|
| cream | `#f2ede5` | фон студии |
| paper | `#fbf8f3` | поверхность телефона/desk |
| ink | `#1c1915` | заголовок и primary CTA |
| ink-2 | `#6d6358` | пояснение |
| gold | `#b8955a` | рамка слота, secondary border |
| mint soft | `#dce8df` / `#3d7a5c` | роль, empty chip, nav current |
| terra | `#8f3d2d` + `#f9e7e9` | error alert (`cabinet-alert`) |

Мотив: **тонкая золотая рамка** вокруг выбранного empty/error card — выбор состояния, не бронь.  
На 390 один primary ≥ 44px; secondary внизу (sticky) или рядом на 1440.  
`prefers-reduced-motion`: рамка статична, скелетон без пульса.

## Общая оболочка

| Состояние | Что на кадре | CTA |
|---|---|---|
| L | Shell + nav; content skeletons; primary disabled | — |
| E first-run | Заголовок + честное empty + рамка + один primary | роль-специфичный |
| E list-empty | Список пуст при уже настроенном профиле | secondary «обновить» / фильтр |
| R | Alert `role=alert` + ghost rows + сохранить chrome | «Повторить» |
| F | Нет org / чужая org | «Выбрать организацию» / «Войти» |
| M | Как L/E/R без пульса и подъёма | те же CTA |

## Customer `/cabinet/customer`

| Экран | E | R |
|---|---|---|
| Home | «Пока нет активных событий.» CTA «Собрать событие» | «Не удалось загрузить кабинет.» + Повторить |
| Favorites | «В избранном пусто.» CTA «Открыть каталог» | Повторить без очистки |
| Messages | «Переписок ещё нет.» | «Не удалось загрузить сообщения.» |
| Saved searches | «Нет сохранённых поисков.» CTA «Найти артистов» | Повторить |

## Performer `/cabinet/performer`

| Экран | E | R |
|---|---|---|
| Home (first) | Checklist: витрина → слот → ждать заявку | API fail на dashboard widgets |
| Requests | «Здесь будут новые заявки.» | «Не удалось загрузить заявки.» сумма/черновик не терять |
| Calendar | «Пока нет открытых дат.» CTA «Настроить доступность» | Ошибка календаря + Повторить |
| Services | «Добавьте первую услугу.» | Ошибка сохранения услуги |
| Messages | «Пока нет диалогов.» | Повторить |

## Venue `/cabinet/venue`

| Экран | E | R |
|---|---|---|
| Home без venue | «Сначала создайте площадку.» | Fail create/load |
| Halls | «Добавьте первый зал.» | Повторить список залов |
| Requests | «Заявок пока нет.» | Повторить |
| Calendar | «Календарь начинается с площадки.» | Повторить |
| Messages | «Переписок нет.» | Повторить |

## A11y в preview

- Error: `role="alert"`.  
- CTA: min-height 44px, видимый `:focus-visible`.  
- Декор SVG: `aria-hidden`.  
- Переключатели роли/состояния: `aria-pressed`.

## Live сверка (не redesign)

- Shell: `CabinetPageShell` (`empty` / `error`).  
- Alert live: `.cabinet-alert`.  
- Soft empty: `.workspace-soft-empty`.  
- Preview **не** подменяет runtime.

## Чеклист Figma

- [ ] Customer home/favorites E+R+L+F @1440+390  
- [ ] Performer home checklist + requests/calendar E+R @1440+390  
- [ ] Venue home/halls/calendar E+R @1440+390  
- [ ] Reduced-motion кадр рамки без пульса  
