# BK-DESIGN-TYPE-017 · Выдача 1: роль → регистрация, каталог → профиль

Статус: **PREVIEW**, не опубликовано. Существующее интро Scene 01 не переписано.

## Основа

- Продовый фронтенд bukergo.ru = ветка `codex/booker-integration-20260930` (`ec230ee`) + overlay `infra/web-overlays/scene01-v5-live/` из PR #24 (`a359bc8`). Совпадение проверено по классам живых страниц `/`, `/login`, `/search` (9/9 маркеров).
- Отличие: `baseline_sha256` в `layout-updates.json` (`844944…`) не совпадает ни с одной веткой GitHub (`layout.tsx` в `ec230ee` = `1c528d…`). Значит, на сервере есть правки, которых нет в git. Две замены в layout (`data-booker-theme="cream"`, `themeColor`) внесены вручную в том же смысле. Перед интеграцией нужно сверить их с файлом на хосте.
- Первый коммит ветки переносит overlay в дерево приложения (`app/page.tsx`, `components/Scene01LiveHome.tsx`, `app/scene01-*.css`, `lib/scene01Recovery*`, правка `AuthPage`). Второй коммит содержит саму выдачу.

## Что сделано

| Сцена | Реализация |
|---|---|
| 01 → 02 Роль → регистрация | Интро не тронуто, кроме одной строки в `onChoose`: перед уже существующим `location.assign` в `sessionStorage` записывается прямоугольник фото. `RoleHandoffCard` на `/login` показывает то же фото, тот же kicker и заголовок роли. Фото вырастает из прямоугольника карточки интро (FLIP, 550ms, `E_OUT` интро). Поля появляются через 300–390ms со сдвигом 6px (220ms). Фокус переходит на заголовок формы. На mobile шапка компактная (фото 92–168px), первый input виден без пролёта. «← К выбору роли» и browser Back возвращают к видимым карточкам ролей: работает существующий `scene01Recovery`. |
| 02 Регистрация | Реальный `POST /auth/register` и `createOrgWithConfirm`, роль переносится в `kind`. Ошибка API показывается в `role="alert"`, введённые данные сохраняются. `aria-busy` на кнопке во время отправки. SMS/OAuth не нарисованы. |
| 04 Каталог | Карточки из плотной бумаги: кромка и тёплая контактная тень, свет сверху слева. На desktop наклон ≤5° (`perspective 1200px`, 160ms), только при `hover:hover` и `pointer:fine`. На touch — подъём на 2px и `scale(.99)`. Тёмные заглушки Black Edition заменены кремовой бумагой с золотой serif-монограммой, лаймовые галочки — золотыми. «Фильтры» на mobile — бумажная панель вместо чёрной полосы, раскрывается за 220ms. Отдельные состояния: loading (бумажный skeleton без blur), empty, error. |
| 05 Профиль | Фото карточки каталога разворачивается в обложку профиля (FLIP, 600ms). Если обложка вне экрана, страница открывается сверху. На mobile обложка стоит первой, под ней имя, CTA и календарь. Слоты, тарифы, чипы и схема зала переведены в бумагу и золото. Цена берётся только из API (`Ориентир` / «Цена по запросу»). Back возвращает каталог с теми же фильтрами (URL) и прокруткой. |

## Файлы

- `lib/motion.ts`: motion-пресеты (длительности, easing интро), `prefersReducedMotion`, `saveHandoff`/`takeHandoff` (одноразовые, живут 4s, переживают запрет storage), `playArrival` (FLIP; при reduced motion — fade 140ms; дальний прыжок заменяется мягким появлением).
- `lib/motion.test.ts`: 6 тестов (добавлены в `test:unit` вместе с тестами `scene01Recovery`).
- `lib/sceneRoles.ts`: тексты и фото ролей, зеркало `ROLES` интро.
- `components/scene/HandoffArrival.tsx`, `RoleHandoffCard.tsx`, `usePaperTilt.ts`: переиспользуемые части.
- `app/booker-scene-system.css`: дизайн-токены `--bk-*`, материал бумаги, сцены и слой `booker-scene`. Слой объявлен раньше `booker-cream`, поэтому его `!important` перекрывает и наследие editions, и continuity. Обычные (не important) стили приложения его не перебивают.
- Изменены точечно: `AuthPage.tsx`, `CatalogResultCard.tsx`, `ArtistProfileClient.tsx`, `VenueProfileClient.tsx`, `Scene01LiveHome.tsx` (1 строка + import), `layout.tsx` (import).

## API-контракты (не изменены)

`POST /auth/register`, `POST /auth/login`, `GET /me`, `POST /orgs` (через `createOrgWithConfirm`), `GET /catalog/search`, `GET /categories`, профили артиста и площадки, `POST /commerce/promotion-touches/*`. Новых вызовов и моковых данных нет. Локальная проверка шла на демо-seed API (`BOOKER_ALLOW_DEMO_SEED=1`, sqlite) — это тестовые данные, не прод.

## Запуск preview

```bash
python -m venv .venv && .venv/bin/pip install -e apps/api
cd apps/api && BOOKER_ALLOW_DEMO_SEED=1 BOOKER_DATABASE_URL=sqlite:////tmp/booker-dev.db ../../.venv/bin/python -m booker_api.seed
BOOKER_DATABASE_URL=sqlite:////tmp/booker-dev.db BOOKER_PUBLIC_REGISTRATION_ENABLED=1 BOOKER_ENVIRONMENT=test \
  BOOKER_PAYMENT_PROVIDER=stub BOOKER_PAYMENT_ALLOW_STUB=true BOOKER_COMMERCE_PROVIDER=stub BOOKER_COMMERCE_ALLOW_STUB=true \
  BOOKER_COMMERCE_WEBHOOK_SECRET=local-only ../../.venv/bin/python -m uvicorn booker_api.main:app --port 8000
cd apps/web && npm ci && BOOKER_PUBLIC_REGISTRATION_ENABLED=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 \
  BOOKER_INTERNAL_API_URL=http://127.0.0.1:8000 npx next dev -p 3000
```

## Проверено (Chromium headless, локально)

- 320/390/768/1440: `/login?mode=register&role=customer|venue`, `/search?kind=artist`, пустая выдача, артист, площадка. Горизонтального переполнения нет (24/24).
- Роль → регистрация: handoff срабатывает, `kind=artist`, фокус на H1. Back показывает 3 карточки ролей (`bk-reg`), Forward возвращает шапку «Исполнитель». То же на 390px.
- Каталог → профиль: handoff срабатывает. Back восстанавливает URL и `scrollY` (260 → 260).
- `prefers-reduced-motion`: переходы заменены коротким fade, наклона нет.
- Ошибка API регистрации («Email уже занят»): данные и роль сохранены. Успешная регистрация площадки ведёт в `/cabinet/venue`.
- Каталог при остановленном API показывает карточку ошибки с «Попробовать ещё раз».
- `tsc --noEmit` и unit-тесты (13) проходят.

## Не проверено и не заявляется

- Реальные iPhone/Android, Safari BFCache, fps. Headless-рендер даёт около 16 fps, и это не мерило.
- Keyboard-only проход интро → роль проверен только для Enter (пропуск/начало); фокус-кольцо карточек интро — как в PR #24.
- Остаток: подпись номера зала (`.profile-hall-icon` во втором варианте разметки) сохраняет зелёный оттенок.
- Сцены 3, 6–14 (первое действие заказчика, дата, сборка события, отправка, сделка, кабинеты) — следующие выдачи.

## Дополнение: сцена «сборка события» и объём переходов

- `components/scene/EventComposition.tsx` на `/assemble`: бумажный стол с перспективой (`rotateX 10°`) и тремя местами — артист, площадка, дата. Читает тот же черновик, что пишет существующий конструктор (`talentIds`, `venueId`), и дату из шага «Когда встречаемся?». Имена и фото берутся из `GET /artists/:id` и `GET /venues/:id`. Пока данные грузятся, в слоте skeleton; при ошибке — честное сообщение. Счётчик «N из 3 · это сборка, не бронь».
- «Добавить в сборку события +» в профиле передаёт прямоугольник обложки (FLIP + подъём к зрителю): карточка перелетает в своё место. Дата ложится как перевёрнутый листок календаря (520ms).
- `playArrival` получил слой объёма (`composite: "add"`): во время переноса подъём на `translateZ` 32px (14px на телефоне), поворот до 9° (4°), тень становится глубже, в конце карточка ложится ровно. Без поддержки composite — обычный FLIP. При reduced motion — fade.
- На телефоне стол не наклонён: три компактные карточки в ряд.
- Существующий пазл конструктора тонирован в тёплый металл, лаймовый акцент заголовка заменён золотом.
- Видео preview записаны Playwright с реального локального потока (desktop 1440 и 390), headless-рендер.
