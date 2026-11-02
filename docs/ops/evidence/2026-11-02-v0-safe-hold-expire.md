# V0-SAFE-HOLD-EXPIRE — Implementation Report

**Date:** 2026-11-02  
**Branch:** `fix/v0-safe-hold-expire`  
**Worktree:** `/home/art67/booker-worktrees/v0-safe-hold-expire`  
**Base:** `0bd7aa0` (`sync/live-canonical-20261031`)  
**Agent workspace:** switched via `move_agent_to_root` to this worktree

## Verdict

**BLOCKED** (full V0 PASS criteria) — PostgreSQL concurrency not run (`TEST_POSTGRES_DSN` absent, Docker unavailable).

**Code + SQLite verification:** PASS (28 passed, 1 skipped postgres).  
**Independent security review:** PASS (no CRITICAL/HIGH).

Scores unchanged: FULL 59,00% / MVP 56,00% / Design 15,00%.

## Root cause

`expire_holds` opened held slots on TTL but cancelled booking only in `DateHeld`. Webhook confirmed without alive owned hold check.

## Invariants changed

- Exclusive statuses cancel on expire: DateHeld, AwaitingContract, AwaitingPayment
- Confirm requires alive hold + slot ownership
- Late payment: money kept + `payment.requires_review`, no auto-confirm
- Expire commits before contract/payment ops that may 409
- Consume via audit `hold.consumed` + hold status `cancelled` (no migration)

## Files

- `apps/api/booker_api/booking_holds.py` (new)
- `apps/api/booker_api/routers/deals.py`
- `apps/api/booker_api/routers/payments.py`
- `apps/api/tests/test_hold_expire_v0.py`
- `apps/api/tests/test_hold_expire_postgres.py`
- `docs/product/CONTRACT.md`
- `docs/adr/ADR-HOLD-001-atomic-expire.md`

## Tests

| Suite | Result |
|---|---|
| test_hold_expire_v0 + holds + hold_race + payments | 28 PASS |
| test_hold_expire_postgres | 1 SKIP (no DSN) |
| ruff | PASS |
| C08 non-threaded acceptance | 1 PASS |
| C08 threaded SQLite | not claimed (segfault risk / not PG proof) |

## Risks for in-flight deals

`count_stale_exclusive_holds()` inventories past-TTL exclusive bookings. Production mass cancel not performed. Release must run inventory on staging copy first.

## Blocked

1. PostgreSQL expire↔webhook concurrency proof  
2. Merge / port to delivery / production deploy  

## Next

Provide `TEST_POSTGRES_DSN` for full V0 PASS, or continue independent Artist IA gaps without claiming V0 complete.
