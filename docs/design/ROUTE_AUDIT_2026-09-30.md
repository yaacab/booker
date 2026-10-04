# Букер — read-only route audit, 30.09.2026

## Снимок и границы

- HEAD: `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907` (`feat/sitewide-lime-design`, на момент проверки на 1 коммит впереди `origin/feat/sitewide-lime-design`).
- Сопоставлены текущие HEAD **и dirty tree** с `docs/design/SCREEN_FLOW_MAP.md`, `docs/design/SCREEN_REFERENCE_ATLAS.md` и продуктовым `docs/product/CONTRACT.md`. Карта, атлас и план 18 кадров на момент проверки были untracked; контракт, часть API и веб-компонентов имели незакоммиченные изменения. Результат нельзя автоматически переносить на чистый HEAD или другой checkout.
- `outputs/` и worktrees не просматривались. Untracked `apps/web/app/investor/` замечен как дрейф дерева и не входит в 75 пользовательских семейств.
- После этого read-only снимка локально исправлена проверка плательщика и ключа повтора в `A/payments.py`; 23 связанных теста ACL/платежей прошли во временном окружении. Пункт 1 раздела «Действия по пробелам» ниже описывает находку на момент аудита, а не текущее состояние патча. Остальные пункты открыты.
- Это статическое сопоставление маршрутов и вызовов. **Runtime, доступность страниц, роли и ACL в живом приложении, API E2E, мобильные состояния, платёжный партнёр и production не проверены.** Наличие route-файла не доказывает завершённость сценария.
- Правило продукта: цены, комиссии и возвраты — только API; live-платежи закрыты до юриста и партнёра/U5. `blocked` ниже обозначает этот продуктовый гейт, а не ошибку сборки.

Обозначения в таблицах: `W/` = `apps/web/app/`, `C/` = `apps/web/components/`, `A/` = `apps/api/booker_api/routers/`. Это точные относительные пути файлов; `—` означает, что отдельного Next.js route-файла нет. `exists` — route и основное действие видны в коде; `partial` — route, вкладка или API есть, но ключевая часть целевого сценария отсутствует; `missing` — пригодного экрана нет; `blocked` — live-сценарий отложен контрактом. API в каждой строке — релевантный найденный файл, не утверждение о полном соответствии контракту.

## 75 семейств

| № | Семейство | Статус | Фактический Next.js route-файл | Релевантный API-файл | Краткое свидетельство / разрыв |
|---:|---|---|---|---|---|
| 01 | Главная | exists | `W/page.tsx` | — | Переходы в поиск и создание события. |
| 02 | Каталог | partial | `W/search/page.tsx` | `A/catalog.py` | Поиск есть; полнота публикации и актуальность карточек требуют проверки. |
| 03 | Исполнитель | partial | `W/artists/[id]/page.tsx`; `C/ArtistProfileClient.tsx` | `A/catalog.py` | Профиль, слоты и запрос есть; отдельного портфолио нет. |
| 04 | Площадка | partial | `W/venues/[id]/page.tsx`; `C/VenueProfileClient.tsx` | `A/catalog.py` | Профиль и залы есть; полный выбор зала и условий не доказан. |
| 05 | Сравнение | exists | `W/compare/page.tsx` | `A/shortlists.py` | Сравнение вариантов реализовано. |
| 06 | Совместная подборка | partial | `W/s/[token]/page.tsx`; `C/SharedShortlistClient.tsx` | `A/shortlists.py` | Token и отзыв доступа есть; совместные комментарии не подтверждены. |
| 07 | Открытые брифы | partial | `W/briefs/page.tsx` | `A/briefs.py` | Публикация и список есть; отклика supply в UI нет. |
| 08 | Новая заявка | partial | `W/events/new/page.tsx` | `A/deals.py` | Создание события есть; пять шагов, автосохранение и перепроверка не подтверждены. |
| 09 | Control Room | partial | `W/events/[id]/page.tsx` | `A/deals.py` | Позиции, сделки и Event Day есть; единая ролевая хронология не подтверждена. |
| 10 | Deal Room: обзор | exists | `W/deals/[id]/page.tsx` | `A/deals.py` | Обзор брони и статусов. |
| 11 | Переписка сделки | partial | `W/deals/[id]/page.tsx` (`chat`) | `A/deals.py` | Сообщения и защищённые вложения сделки есть; прямой ссылки на вкладку и retry нет. |
| 12 | Условия | partial | `W/deals/[id]/page.tsx` (`terms`) | `A/deals.py` | Версия оффера есть; deep link и сравнение версий отсутствуют. |
| 13 | Документы | partial | `W/deals/[id]/page.tsx` (`documents`) | `A/payments.py`; `A/deals.py` | Список, подпись, карантин и выдача с проверкой SHA-256 есть; реального AV и object storage нет. |
| 14 | Деньги сделки | partial | `W/deals/[id]/page.tsx` (`payments`) | `A/payments.py` | Аванс, остаток, обеспечение, внешний отчёт и возврат моделируются; payout/reconciliation и live partner закрыты. |
| 15 | Спор | partial | `W/deals/[id]/page.tsx` (`dispute`) | `A/deals.py`; `A/admin.py` | Открытие спора есть; карточки доказательств и хронологии нет. |
| 16 | Кабинет заказчика | exists | `W/cabinet/customer/page.tsx` | `A/deals.py` | Обзор своих событий и действий. |
| 17 | Избранное | exists | `W/cabinet/customer/favorites/page.tsx`; `C/FavoritesListClient.tsx` | `A/favorites.py` | Список и управление. |
| 18 | Сохранённые поиски | exists | `W/cabinet/customer/saved-searches/page.tsx` | `A/saved_searches.py` | Поиски и согласие на уведомления. |
| 19 | Сообщения заказчика | exists | `W/cabinet/customer/messages/page.tsx`; `C/MessagesHubClient.tsx` | `A/deals.py` | Один диалог живёт от заявки до Booking: request-only карточка открывается, сообщения идемпотентны, unread отмечается отдельным действием, viewer остаётся в режиме чтения. |
| 20 | Кабинет исполнителя | exists | `W/cabinet/performer/page.tsx` | `A/deals.py`; `A/services.py` | Рабочий обзор. |
| 21 | Календарь исполнителя | partial | `W/cabinet/performer/calendar/page.tsx` | `A/catalog.py` | Секция календаря и слоты; полный обзор held/confirmed не доказан. |
| 22 | Заявки исполнителя | partial | `W/cabinet/performer/requests/page.tsx` | `A/deals.py` | Очередь есть; адресной карточки ответа нет. |
| 23 | Услуги | partial | `W/cabinet/performer/services/page.tsx` | `A/services.py` | Создание услуг есть; версионируемый опубликованный прайс не подтверждён. |
| 24 | Сообщения исполнителя | exists | `W/cabinet/performer/messages/page.tsx`; `C/MessagesHubClient.tsx` | `A/deals.py` | Исполнитель открывает и продолжает request-only переписку до предложения; после оффера тот же conversation переходит в Deal Room. |
| 25 | Кабинет площадки | partial | `W/cabinet/venue/page.tsx` | `A/catalog.py`; `A/trust.py` | Обзор есть; claim не встроен как обязательный путь. |
| 26 | Календарь площадки | partial | `W/cabinet/venue/calendar/page.tsx` | `A/catalog.py` | Секция есть; ограничения монтажа и демонтажа не доказаны. |
| 27 | Залы | partial | `W/cabinet/venue/halls/page.tsx` | `A/catalog.py` | Список/создание есть; полного редактора публикации нет. |
| 28 | Заявки площадки | partial | `W/cabinet/venue/requests/page.tsx` | `A/deals.py` | Очередь есть; отдельное подтверждение зала и слота не доказано. |
| 29 | Статистика площадки | partial | `W/cabinet/venue/stats/page.tsx` | `A/deals.py` | Виджет есть; определения метрик и малые выборки не доказаны. |
| 30 | Сообщения площадки | exists | `W/cabinet/venue/messages/page.tsx`; `C/MessagesHubClient.tsx` | `A/deals.py` | Площадка открывает request-only диалог и отвечает до оффера; после Booking сохраняется тот же conversation. |
| 31 | Вход | partial | `W/login/page.tsx` | `A/identity.py` | Email/password и безопасный `next`; кода подтверждённого контакта нет. |
| 32 | Регистрация | partial | `W/login/page.tsx` (`register`) | `A/identity.py` | Отдельного `/register` нет; версии согласий в форме не видны. |
| 33 | Подтверждение контакта | missing | — | `A/identity.py` | Нет `/verify` и отдельного verify endpoint/TTL-кода. |
| 34 | Выбор роли | partial | `W/login/page.tsx` (`register`) | `A/identity.py` | Роль выбирается при создании org; `/onboarding/role` нет. |
| 35 | Профиль заказчика | partial | `W/profile/page.tsx` | `A/identity.py` | `/onboarding/customer` и его черновика нет. |
| 36 | Организация и команда | partial | `W/profile/page.tsx` | `A/identity.py` | Token invitation с TTL, email binding, revoke/accept, scoped idempotency и CAS есть; UI приглашений и пошаговый onboarding отсутствуют. |
| 37 | Восстановление доступа | partial | `W/login/page.tsx` (`recover/reset`) | `A/identity.py` | Восстановление встроено в login; `/recover` нет. |
| 38 | Платежи по событиям | missing | — | `A/payments.py` | Нет `/payments`; отдельного списка обязательств нет. |
| 39 | Аванс по сделке | blocked | — | `A/payments.py` | Нет `/deals/[id]/payments/advance`; live-аванс до U5 закрыт. |
| 40 | Checkout | blocked | — | `A/payments.py` | Нет `/deals/[id]/checkout`; партнёрский live checkout до U5 закрыт. |
| 41 | Pending | blocked | — | `A/payments.py` | Нет `/payments/[id]/pending` и отдельного серверного экрана ожидания. |
| 42 | Результат платежа | blocked | — | `A/payments.py` | Нет `/payments/[id]/result`; live-результат до U5 закрыт. |
| 43 | История и чеки | blocked | — | `A/payments.py` | Нет `/payments/history` и полного набора чеков/актов. |
| 44 | Возврат | partial | — | `A/admin.py` | Admin refund есть; пользовательского `/payments/[id]/refund` нет. |
| 45 | Выплаты исполнителю | blocked | — | `A/payments.py` | Нет `/cabinet/performer/payouts`; live-выплаты до U5 закрыты. |
| 46 | Уведомления | partial | —; `C/SiteChrome.tsx` | `A/identity.py` | Header вызывает `/notifications`; отдельного `/notifications` нет. |
| 47 | Настройки уведомлений | missing | — | `A/saved_searches.py` | Нет `/settings/notifications`; есть только согласие сохранённого поиска. |
| 48 | Безопасность аккаунта | missing | — | `A/identity.py`; `A/admin.py` | Нет `/settings/security`; admin TOTP не заменяет сессии пользователя. |
| 49 | Админ-очередь | partial | `W/admin/page.tsx` | `A/admin.py`; `A/venue_admin.py` | Проверки, метрики, audit, external confirm; нет цельной SLA/денежной очереди. |
| 50 | Профиль | partial | `W/profile/page.tsx` | `A/identity.py` | Личность/org видны; экспорт, удаление и согласия не показаны. |
| 51 | Поддержка | partial | `W/support/page.tsx` | `A/trust.py`; `A/support_agent.py` | Есть безопасный помощник, отдельная человеческая переписка, close/reopen, закрытые operator notes и обязательная 2FA оператора. Секреты маскируются во всех support-каналах; неявка и платёж без Confirmed получают серверный SLA priority/due. Назначения конкретного оператора ещё нет. |
| 52 | FAQ и документы | partial | `W/faq/page.tsx`; `W/legal/page.tsx`; `W/legal/offer/page.tsx`; `W/legal/privacy/page.tsx`; `W/legal/cookies/page.tsx`; `W/legal/cancellation/page.tsx`; `W/legal/disputes/page.tsx`; `W/legal/suppliers/page.tsx` | — | Страницы есть; юридические тексты остаются черновиками по контракту. |
| 53 | Редактор профиля supply | partial | `W/cabinet/performer/page.tsx`; `W/cabinet/venue/page.tsx` | `A/services.py`; `A/catalog.py` | Onboarding/полнота встроены; отдельного редактора нет. |
| 54 | Медиа и права | partial | — | `A/deals.py`; `A/admin.py` | Карантин вложений сделки есть; отдельного media-редактора, AV и согласия на права нет. |
| 55 | Настройка календаря | partial | `W/cabinet/performer/calendar/page.tsx`; `W/cabinet/venue/calendar/page.tsx` | `A/catalog.py` | Слоты/import есть; экрана гейта ≥30 дней нет. |
| 56 | Статус проверки | partial | `W/cabinet/performer/page.tsx`; `W/cabinet/venue/page.tsx` | `A/admin.py` | Полнота/админ-проверка есть; пользовательского статуса с причинами нет. |
| 57 | Редактор оффера | partial | `W/cabinet/performer/requests/page.tsx`; `W/cabinet/venue/requests/page.tsx` | `A/deals.py` | API версий есть; полноценного редактора не найдено. |
| 58 | Команда и права | partial | `W/profile/page.tsx` | `A/identity.py` | Direct-add и token invitation с TTL/revoke/accept есть; UI приглашения и список статусов ещё не реализованы. |
| 59 | Подтверждение площадки | missing | — | `A/trust.py` | Claims API есть; пользовательского claim-flow нет. |
| 60 | Редактор зала | partial | `W/cabinet/venue/halls/page.tsx` | `A/catalog.py` | Добавление зала есть; полный редактор тарифа/медиа/ограничений не подтверждён. |
| 61 | Event Day | partial | `W/events/[id]/page.tsx` | `A/deals.py` | Day-status, check-in/out, offline-pack есть; ролевая хронология/свежесть не доказаны. |
| 62 | Приёмка этапа | missing | — | `A/deals.py` | Check-out не даёт отдельной двусторонней приёмки. |
| 63 | Инцидент | partial | `W/events/[id]/page.tsx`; `W/support/page.tsx` | `A/deals.py`; `A/trust.py` | Общие пути есть; контекстного incident-flow нет. |
| 64 | Внешняя инструкция | partial | `W/deals/[id]/page.tsx` (`payments`) | `A/payments.py` | External mode объясняет прямой перевод и ограничение ответственности; реквизиты получателя не подтверждены партнёром. |
| 65 | Доказательство перевода | partial | `W/deals/[id]/page.tsx` (`payments`) | `A/payments.py` | Заказчик отправляет reference/details с idempotency key; бинарного документа пока нет. |
| 66 | Проверка документа | partial | — | `A/admin.py` | Оператор может учесть сведения или запросить уточнение; отдельной очереди/SLA документа нет. |
| 67 | Учтён оператором | exists | `W/deals/[id]/page.tsx` (`payments`) | `A/admin.py`; `A/payments.py` | Решение пишет `external_recorded` без capture/ledger и показывает статус сторонам. |
| 68 | Внешний возврат | missing | — | `A/admin.py` | Отдельного процесса документов/согласования нет. |
| 69 | Проверка профиля | partial | `W/admin/page.tsx` | `A/admin.py` | Очередь verifications есть; отдельной карточки с доказательствами нет. |
| 70 | External-платежи | partial | `W/admin/page.tsx` | `A/admin.py` | Отчёт и независимое review разделены; очереди документов и сверки реквизитов нет. |
| 71 | Сверка | partial | — | `A/payments.py`; `A/admin.py`; `A/money_movements.py` | Append-only реестр фактических capture/refund есть; live reconciliation с партнёром и экран отсутствуют. |
| 72 | Подтверждение возврата | exists | — | `A/admin.py` | Pending-заявку исполняет только второй администратор со своей сессией и TOTP. |
| 73 | Очередь выплат | blocked | — | `A/payments.py`; `A/admin.py` | Нет полноценной payout-очереди до U5. |
| 74 | Карточка спора | partial | `W/admin/page.tsx` | `A/admin.py`; `A/deals.py` | Спор создать можно; отдельной операторской карточки нет. |
| 75 | 403 / 404 / offline | partial | `W/not-found.tsx`; `W/error.tsx`; `W/global-error.tsx` | — | Общие состояния есть; единый приватный 403/offline с безопасным retry не подтверждён. |

## 18 дополнительных детальных кадров

Все 18 указаны в `docs/product/MARKETPLACE_MATURITY_PLAN.md` и **не представлены отдельными HTML-кадрами атласа**. Колонка ниже описывает только найденную опору в текущем приложении/API; отдельный Next.js route не обязателен до утверждения дизайна.

| Кадр | Статус | Фактические файлы / свидетельство |
|---|---|---|
| Портфолио артиста | partial | `C/ArtistProfileClient.tsx`; отдельного медиа/райдера нет. |
| Реальные отзывы | partial | `A/reviews.py`; отдельной детальной страницы нет. |
| Лента брифов supply | partial | `W/briefs/page.tsx`; общая лента без supply-отклика. |
| Отклик на бриф | missing | `A/briefs.py` содержит `/briefs/{brief_id}/responses`; UI нет. |
| Почему показан вариант | missing | `W/search/page.tsx`; причины сортировки отдельным кадром не раскрыты. |
| Повторное событие | missing | `W/events/[id]/page.tsx`; действия копирования в редактируемый черновик нет. |
| Репутация supply | partial | `A/reviews.py`; отдельного экрана с периодом/знаменателем нет. |
| Хронология события по роли | partial | `W/events/[id]/page.tsx`; цельного ролевого потока нет. |
| Инцидент Event Day | missing | `W/events/[id]/page.tsx`; контекстной карточки нет. |
| Supply CRM | missing | `W/cabinet/performer/page.tsx`; списка приглашений и причин непубликации нет. |
| SLA-очередь | missing | `W/admin/page.tsx`; очереди со сроком и владельцем нет. |
| Risk/reconciliation | blocked | `A/payments.py`; `A/admin.py`; зависит от разделённой модели денег и live-гейта. |
| Карточка адресной заявки | partial | `W/cabinet/performer/requests/page.tsx`; `W/cabinet/venue/requests/page.tsx`; отдельной карточки нет. |
| Новое обращение | partial | `W/support/page.tsx`; помощник и человеческая форма работают с idempotency, но связь с объектом в UI ещё не передаётся. |
| Карточка обращения | exists | `W/support/page.tsx`; диалог, ответ, close/reopen и восстановление assistant session проверены browser E2E. |
| Детали денежного обязательства | missing | `W/deals/[id]/page.tsx`; показывает payment, не обязательство с версиями/попытками. |
| Проверка внешнего документа оператором | missing | `W/admin/page.tsx`; `A/admin.py`; confirm по ID без документа/сверки/причины решения. |
| Приглашение в организацию | partial | `A/identity.py` содержит token invitation с TTL/revoke/accept, строгой email-валидацией и защищённой доставкой; пользовательского UI и списка статусов нет. |

## Действия по пробелам

1. Добавить утверждённую карточку request-only переписки и устойчивый deep link; backend уже сохраняет один conversation от заявки до Booking.
2. Перевести unread с временных меток на монотонный sequence/cursor и зафиксировать участников диалога, чтобы новые сотрудники не получали старую историю автоматически.
3. Завершить путь бриф → адресная заявка → редактор версии оффера. Вкладки `W/deals/[id]/page.tsx` сейчас локальный `useState`, поэтому нужен устойчивый deep link после refresh.
4. Довести контактное подтверждение, UI приглашений команды, claim площадки, права на медиа и календарный горизонт ≥30 дней до цельного пути публикации.
5. Добавить карточку обращения с историей/reopen, контекстный инцидент Event Day, двустороннюю приёмку и offline/устаревшие состояния.
6. Держать live-сценарии 39–45 и 71–73 за U5: юридическая схема, партнёр, webhook/reconciliation и настоящее независимое второе решение по возврату.

Отдельные дизайн-кадры и состояния подлежат утверждению владельцем до редизайна кода. Этот документ не утверждает дизайн и не разрешает платёжный production.
