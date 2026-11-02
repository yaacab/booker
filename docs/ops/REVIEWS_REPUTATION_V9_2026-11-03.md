# REV-02 / V9 — двусторонние отзывы и репутация (локально)

**Дата:** 2026-11-03  
**Уровень:** локально (не staging / не production)  
**Статус:** API + Deal Room + публичные профили + виджеты кабинетов

## Контракт

- Отзыв только после `Completed`.
- Одна запись на (booking, author).
- Цель — организация контрагента, не своя.
- Средняя оценка (`average_rating` / `show_rating`) — только при **≥ 10** отзывов (`review_facts.RATING_THRESHOLD`).

## Поверхности

| Поверхность | Путь |
|---|---|
| Создание | `POST /bookings/{id}/reviews` |
| Список + reputation | `GET /organizations/{id}/reviews`, `/artists/{id}/reviews`, `/venues/{id}/reviews` |
| Reputation | `GET /organizations/{id}/reputation` |
| Deal Room | поле `reviews` в `GET /deal-room/{id}` |
| Каталог | `facts.reviews` / `facts.show_rating` / `facts.note` у артиста и площадки |
| Web Deal Room | `DealReviewPanel` на вкладке «Сводка» |
| Публичные профили | `OrgReviewsBlock` |
| Кабинеты | `ReputationWidget` (артист / площадка) |

## Проверка

```bash
cd apps/api && python -m pytest tests/test_reviews.py -q
```

Ожидаемо: все тесты в `test_reviews.py` PASS, включая порог 10 отзывов, projection в deal-room и факты каталога.

## Не закрывает

- Staging/p95 и production.
- Звёзды в UI до порога 10 (намеренно).
- Платежи / merge в main без отдельного GO.
