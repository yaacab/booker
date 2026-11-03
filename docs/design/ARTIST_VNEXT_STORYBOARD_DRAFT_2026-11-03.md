# Artist vNext — 10 сторибордов (DRAFT)

**Статус:** DRAFT. Не Identity redesign. Не смена `CONTRACT.md`. Не перенос в production UI.  
**Граница:** публичный профиль артиста и кабинет исполнителя в рамках текущего канона публикации/слотов/оффера.  
**Связь:** `ART-07` IN PROGRESS (draft only); утверждение/перенос — после `OWN-DESIGN-ACK`.

## Зачем DRAFT сейчас

Нужен согласованный IA-пакет для дизайна и ревью, чтобы `ART-07` не ждал staging/OAuth/платежей. Перенос в web и смена маршрутов — отдельный GO.

## 10 сторибордов

| # | Сториборд | Кадры (минимум) | CONTRACT-границы |
|---|---|---|---|
| 1 | Первый визит в кабинет исполнителя | empty profile → checklist → first slot | без обещания live payout |
| 2 | Заполнение витрины | media + rights attest → preview | права медиа обязательны до publish |
| 3 | Календарь слотов | free → held → conflict | held ≠ confirmed |
| 4 | Входящая заявка | list → detail → amount → offer | цена/комиссия с сервера |
| 5 | Deal Room со стороны supply | terms version → ack → hold wait | новая цена = новая версия |
| 6 | Публичный профиль visitor | gallery → slots → CTA add-to-event | недоступная дата названа явно |
| 7 | Черновик vs опубликовано | draft banner → publish gate fail/pass | eligibility серверный |
| 8 | Сообщения до оффера | request thread → offer sent | тот же conversation после booking |
| 9 | Мобильный ответ на заявку | 390 requests inbox → create offer | keyboard/focus |
| 10 | Ошибка и отказ | API error retry; decline with reason | без утечки чужих org |

## Что можно делать автономно

- Уточнять copy/IA в docs (этот файл + ссылки на атлас).  
- Сверять route audit с фактическим `cabinet/performer/*` и e2e.  
- Готовить Figma frames **как DRAFT** в дизайн-проекте.

## Что нельзя без владельца

- Утверждать визуальный язык и переносить в `apps/web` как канон (`OWN-DESIGN-ACK`, затем `V05`).  
- Identity redesign (отдельный контур от `AUTH-04`).  
- Live выплаты/реквизиты (`PAY-06`, legal/pay GO).

## Приоритетные кадры 1 / 4 / 6 / 9 (DRAFT frame list)

### 1. Первый визит в кабинет
1. Empty home — checklist 3 пункта (витрина, слот, заявка).  
2. После первого слота — banner «черновик, не в каталоге».  
3. Mobile 390: checklist на всю ширину, один primary CTA.

### 4. Входящая заявка
1. Список «новые» с unread dot.  
2. Detail: дата, бюджет заказчика, поле суммы, hint комиссии «посчитает сервер».  
3. Submit → Deal Room (не отдельный «успех» без booking id).  
4. Error: «Не удалось создать предложение» + сохранить сумму.

### 6. Публичный профиль visitor
1. Gallery + facts + CTA «Добавить в событие».  
2. Недоступная дата — chip «занято», CTA не притворяется броню.  
3. Signed-out CTA → login?next=profile.  
4. 390: sticky bottom CTA без перекрытия галереи.

### 9. Мобильный ответ на заявку
1. `/cabinet/performer/requests` @390.  
2. Выбор заявки с клавиатуры → сумма → «Создать предложение».  
3. Reduced-motion: без анимации панелей.

## Следующий шаг

Сториборды 1/4/6/9 — приоритет для Figma DRAFT (совпадают с V04 key-path gaps). Не менять CONTRACT.
