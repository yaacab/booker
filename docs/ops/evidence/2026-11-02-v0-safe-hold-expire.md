# V0-SAFE-HOLD-EXPIRE — Implementation Report

**Date:** 2026-11-02  
**Branch:** `fix/v0-safe-hold-expire`  
**Worktree:** `/home/art67/booker-worktrees/v0-safe-hold-expire`  
**Base:** `0bd7aa0` (`sync/live-canonical-20261031`)  
**Agent workspace:** switched via `move_agent_to_root` to this worktree

## Verdict

**PASS** (V0 technical criteria locally). Merge / port to delivery / production remain NO-GO.

**Code + SQLite verification:** PASS.  
**PostgreSQL 16 concurrency + integration:** PASS.  
**Independent security review:** PASS (no CRITICAL/HIGH; earlier in slice).

Scores unchanged: FULL 59,00% / MVP 56,00% / Design 15,00%. Closing the PG blocker does not change registry weights.

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
- `apps/api/alembic/versions/f05c6d7e8f90_actor_attribution.py` (PG boolean dialect for ack/sign backfill)
- `apps/api/tests/test_postgres_integration.py` (head revision + irreversible-downgrade seed path)
- `infra/schema-release-manifest.v1.json` (sha256 for migration fix)
- `docs/product/CONTRACT.md`
- `docs/adr/ADR-HOLD-001-atomic-expire.md`

## Local PostgreSQL 16 test runtime

| Item | Value |
|---|---|
| Version | PostgreSQL 16.15 (user-space Theseus build) |
| Bind | `127.0.0.1:55432` only (not public 5432) |
| Data dir | `~/.local/share/booker-pg16-test/data` |
| Role/DB | `booker_test` / `booker_test` (no production data) |
| DSN | `TEST_POSTGRES_DSN` in `~/.config/booker/test-postgres.env` (mode 600, not in Git) |

## Tests

| Suite | Result |
|---|---|
| test_hold_expire_v0 + hold_race | PASS |
| test_hold_expire_postgres (6 concurrency/scenario) | 6 PASS |
| `-m postgres_integration` | 14 PASS |
| schema-release head/manifest | PASS |
| Full API pytest with DSN | 860 PASS / 1 FAIL then fixed → schema PASS; final focused 26 PASS |
| ruff | PASS (prior) |
| C08 threaded SQLite | not claimed as PG proof |

### PostgreSQL concurrency covered

- Expire vs webhook: one winner; never Confirmed + open slot
- Parallel holds on same slot: 200 + 409, one active hold
- Confirm after expire → `requires_review`, booking Cancelled, slot open
- Foreign hold slot → `requires_review`, stays AwaitingPayment
- Webhook redelivery idempotent after Confirmed
- Concurrent late payment notices after cancel: review or ignored_terminal; never re-confirm

## Risks for in-flight deals

`count_stale_exclusive_holds()` inventories past-TTL exclusive bookings. Production mass cancel not performed. Release must run inventory on staging copy first.

## Still NO-GO

1. Merge / port to delivery  
2. Production deploy  
3. Real payments  

## Next

Artist Profile & Services gaps in a separate working branch (no Identity redesign).
