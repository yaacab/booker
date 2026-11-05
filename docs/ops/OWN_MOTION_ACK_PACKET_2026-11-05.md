# OWN-MOTION-ACK — пакет решения · 2026-11-05

Короткий packet для явного ACK владельца. **Не** считает motion утверждённым, пока нет ответа YES/NO ниже.

## Что утверждается

Конкретный motion **«Рамка слота» v2** из:

- `docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md`
- интерактивный preview: `docs/design/previews/motion-slot-frame-v2.html` → `/design-previews/motion-slot-frame-v2.html`

## Границы ACK

| Входит | Не входит |
|---|---|
| Тёмная сцена, 3 шага Люди/Место/Дата, рамка 480 ms, CTA с первого кадра | Перенос в `apps/web` (это `D05` после ACK) |
| `prefers-reduced-motion` / keyboard / без autoplay | Higgsfield/ambient video в продукт |
| Preview-only, без цены/hold/оплаты | Права на внешние шрифты/видеоассеты (отдельная проверка в D05) |

## Как принять решение

1. Открыть `/design-previews/motion-slot-frame-v2.html` (локально или после merge).  
2. Проверить @390 и @1440: шаги 01–03, Tab/focus, reduced-motion (OS).  
3. Ответить одной строкой в чат или в этот файл:

```text
OWN-MOTION-ACK: YES | NO
дата:
комментарий (если NO — что менять в preview):
```

## После YES

1. Задача `OWN-MOTION-ACK` → DONE + evidence этот файл + SHA.  
2. `D05`/`V06` — интеграция в web с fallback.  
3. Formal `V07`/`D06` — только после интеграции + a11y/mobile proof (staging для V08).

## После NO

Меняется только preview; код продукта не трогаем. Новый packet с датой.
