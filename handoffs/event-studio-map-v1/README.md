# Event Studio Map v1 — handoff для Cursor

Это отдельный, не подключённый к production пакет интерфейса «Соберите событие» для «Букера». Он переводит выбранный визуальный эталон в самостоятельный React/Next.js компонент и не меняет текущий пользовательский сценарий проекта.

## Что внутри

- `reference.webp` — утверждённый визуальный ориентир в компактном формате.
- `EventStudioMap.tsx` — интерактивный клиентский компонент без сторонних UI-зависимостей.
- `event-studio-map.css` — адаптивные стили desktop/tablet/mobile.
- `integration-adapter.example.ts` — граница между интерфейсом и API.
- `CURSOR_PROMPT.md` — готовое задание Cursor для интеграции.
- `INTEGRATION_CHECKLIST.md` — критерии готовности.

## Продуктовый смысл

Публичный поиск остаётся эмоциональным и визуальным, а сбор события становится простой «живой картой»: в центре событие, вокруг него место, дата, команда и условия. Правая панель меняет контекст, но пользователь не покидает сборку. После подтверждения отдельных позиций работа продолжается в профессиональных Event Control Room и Deal Room.

## Неподвижные правила

1. Клиент не рассчитывает окончательную цену, комиссию, возврат или платёжный график.
2. Ориентир бюджета визуально обозначается ориентиром. Итог приходит только в серверной `OfferVersion` с `quote_id`.
3. Выбор исполнителя не равен брони. Состояния `request → offer → confirmation → hold → deal` остаются раздельными.
4. Одна позиция состава создаёт отдельный Request/Deal; Event объединяет их в общий Control Room.
5. Hold должен быть серверным, конкурентным, идемпотентным и иметь точное время истечения.
6. Добровольный гарант нельзя показывать активным до подключения партнёра и согласия обеих сторон.
7. Автосохранение должно иметь статусы `saving/saved/error`, а не декоративный текст.

## Предлагаемая интеграция

1. Скопировать компонент в `apps/web/components/event-studio/EventStudioMap.tsx`, CSS — рядом или разложить по существующим токенам.
2. Подключить компонент в текущем маршруте создания события за feature flag `event_studio_map_v1`.
3. Заменить mock-данные адаптером существующих Event, Requirement, Profile, VenueUnit и Availability API.
4. Сохранять черновик с debounce 600–900 мс и серверной версией для защиты от перезаписи.
5. После шага «Проверка» создать Event, затем отдельные Request для выбранных позиций.
6. Получать бюджет как диапазон агрегированных серверных ориентиров; после OfferVersion показывать точные суммы и `quote_id`.
7. Добавить аналитику по шагам и E2E-сценарии из чек-листа.

## События аналитики

`event_studio_opened`, `event_stage_viewed`, `venue_selected`, `date_changed`, `talent_filter_used`, `talent_added`, `talent_removed`, `compatibility_warning_opened`, `draft_saved`, `review_opened`, `event_submitted`.

## Быстрый локальный пример

```tsx
import EventStudioMap from "@/components/event-studio/EventStudioMap";

export default function NewEventPage() {
  return <EventStudioMap onDraftChange={saveDraft} onContinue={submitEvent} />;
}
```

Перед merge Cursor должен сохранить существующий API-контракт и продуктовые ограничения из `AGENTS.md` и `docs/product/CONTRACT.md`.
