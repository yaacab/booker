# ADR-HOLD-001 — Atomic BookingHold expiry for exclusive bookings

**Status:** Accepted (GO-G4-V0-SAFE-HOLD, 2026-11-02)  
**Base:** `sync/live-canonical-20261031` @ `0bd7aa0`  
**Branch:** `fix/v0-safe-hold-expire`

## Context

`expire_holds` freed `AvailabilitySlot` whenever a hold TTL elapsed, but cancelled the `Booking` only in `DateHeld`. After transition to `AwaitingContract` / `AwaitingPayment`, an expired hold could open the slot while the deal remained active. Payment webhooks then confirmed without checking an alive owned hold, enabling double booking.

## Decision

Adopt **Variant A**:

1. Exclusive booking statuses while a hold is active: `DateHeld`, `AwaitingContract`, `AwaitingPayment`.
2. On TTL: atomically `hold → expired`, booking → `Cancelled`, request → `Cancelled`, slot → `open` only if still `held` by this hold.
3. Never open a `confirmed` slot from expiry.
4. On advance payment success: confirm only with active unexpired hold whose `slot_id` matches `booking.slot_id` and `slot.status == held`; then audit `hold.consumed` and set hold status to existing terminal `cancelled` (no DB migration / no new enum).
5. Late or unowned payment success: keep money movement, set response `requires_review`, audit `payment.requires_review`, do not confirm.
6. Lock order: `Booking → BookingHold → AvailabilitySlot` (webhook locks `Payment` first, then the same chain).

## Consequences

- Mid-flight deals past TTL cancel on next expire tick — intentional safety.
- CONTRACT.md documents `AwaitingContract` and hold invariants.
- Request status enum sync remains a separate task.
- PostgreSQL concurrent expire-vs-confirm requires `TEST_POSTGRES_DSN`; without it V0 concurrency proof is BLOCKED.

## Alternatives rejected for V0

- **B** finite extend without atomic cancel — deferred; may layer later with caps.
- **C** keep slot held indefinitely — infinite block risk.
- Dual-write / `ResourceReservation` — out of scope.
