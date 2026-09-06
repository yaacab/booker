# Риски и гейты (честно)

## Что уже ок для diligence

- Ядро сделки на сервере (quote, hold, статусы, audit).
- External-payment как мост до U5.
- Founding seed + честная разметка open-data площадок.
- Ops runbooks (`docs/ops/PROD_INFRA.md`), restore drill — фиксировать в логе.

## Риски (говорить вслух)

| Риск | Митигация |
|------|-----------|
| Юрлицо / OPERATOR пустые | Не позиционировать как «regulated marketplace»; баннер draft |
| Нет live-эквайринга | External + путь U5; не слово «эскроу» |
| Seed ≠ traction | Метка seeded в `METRICS_SNAPSHOT`; 5–10 design-partner сделок |
| Асимметрия venue/artist | Wave D artists + playbook outreach |
| SQLite на prod | CONTRACT: ок для малого concierge; Postgres — P0, staging-пруф |

## Гейты

| Гейт | GO | STOP |
|------|----|------|
| Пиitch diligence | Демо по скрипту, external понятен, docs/investors заполнены | Враньё про страховку/live |
| Alpha → paid (U5) | Юрист + партнёр *или* осознанный external; object auth | Ложная «защита», нет restore |
| 10 → 30 deals | fill ≥70%, offer <2h, double-book 0 | Сделки вне продукта |

Блокеры уровня 3: см. `OWNER_GATES.md`.
