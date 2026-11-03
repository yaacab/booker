# C08 hold exclusivity — sequential vs concurrent coverage

**Дата:** 2026-11-03

## Что не является race-proof

`tests/test_acceptance_c04_c08.py::test_c08_hold_exclusivity_same_slot` — **последовательный** SQLite/TestClient тест. Он доказывает инвариант «ровно один active hold на слот», но **не** конкурентный interleaving.

Shared TestClient в потоках давал флаки `401/404/[409,409]` и зависания — не harness.

## Конкурентное покрытие

`tests/test_postgres_integration.py::test_postgres_concurrent_hold_same_slot_only_one_succeeds`

- opt-in: `TEST_POSTGRES_DSN`
- две независимые SQLAlchemy-сессии + `Barrier`
- вызов `deals.hold_booking` (не shared TestClient threads)
- ожидание `sorted == [200, 409]` и ровно один `BookingHold(status=active)`

```bash
TEST_POSTGRES_DSN='postgresql+psycopg://…' \
  uv run --extra dev pytest tests/test_postgres_integration.py::test_postgres_concurrent_hold_same_slot_only_one_succeeds -q
```

Без DSN тест SKIP — это не PASS race-proof на CI без Postgres.
