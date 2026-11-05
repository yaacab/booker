# V04 — Cabinet empty / error states (DRAFT)

**Статус:** DRAFT. Не перенос в `apps/web`. Preview: `docs/design/previews/cabinet-empty-error.html`.  
**Роли:** customer / performer / venue. Viewports: 1440 + 390.  
**Правила:** цена/комиссия только «из API»; held ≠ confirmed; без Identity redesign.

## Общая оболочка

| Состояние | Что на кадре | CTA |
|---|---|---|
| L | Shell + nav; content skeletons | disabled primary |
| E first-run | Заголовок кабинета + честное empty + один primary | роль-специфичный |
| E list-empty | Список пуст при уже настроенном профиле | secondary «обновить» / фильтр |
| R | Banner/alert + сохранить chrome | «Повторить» |
| F | Нет org / нет доступа | «Выбрать организацию» / «Войти» |
| M | Без пульсации скелетонов | статичный placeholder |

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

## Live сверка (не redesign)

- Shell: `CabinetPageShell` (`empty` / `error` props).  
- Soft empty уже в виджетах (`workspace-soft-empty`).  
- Этот пакет фиксирует **канон copy + иерархию** для Figma; web не меняем в этом PR.

## Чеклист Figma

- [ ] Customer home/favorites/messages E+R @1440+390  
- [ ] Performer home/requests/calendar E+R @1440+390  
- [ ] Venue home/halls/requests E+R @1440+390  
