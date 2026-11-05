"""BookingHold lifecycle helpers — exclusive reservation until confirm or atomic expiry."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from booker_api.models import (
    AvailabilitySlot,
    Booking,
    BookingHold,
    Conversation,
    Message,
    Offer,
    Request,
)
from booker_api.security import audit, aware, now

# Bookings that assume exclusive use of a held slot while a hold is active.
EXCLUSIVE_BOOKING_STATUSES = frozenset({"DateHeld", "AwaitingContract", "AwaitingPayment"})


def active_hold_for_booking(
    db: Session, booking_id: str, *, for_update: bool = False
) -> BookingHold | None:
    query = db.query(BookingHold).filter(
        BookingHold.booking_id == booking_id,
        BookingHold.status == "active",
    )
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()


def hold_is_unexpired(hold: BookingHold, moment: datetime | None = None) -> bool:
    return aware(hold.expires_at) > (moment or now())


def reservation_for_booking(
    db: Session,
    booking: Booking,
    *,
    for_update: bool = False,
    moment: datetime | None = None,
) -> BookingHold | None:
    """Active unexpired hold that owns booking.slot_id, or None."""
    hold = active_hold_for_booking(db, booking.id, for_update=for_update)
    if hold is None or not hold_is_unexpired(hold, moment):
        return None
    if hold.slot_id != booking.slot_id:
        return None
    return hold


def require_alive_reservation(db: Session, booking: Booking, *, for_update: bool = False) -> BookingHold:
    hold = reservation_for_booking(db, booking, for_update=for_update)
    if hold is None:
        raise HTTPException(409, "Резервирование даты истекло или отсутствует. Нужно удержать дату снова.")
    return hold


def slot_owned_by_hold(slot: AvailabilitySlot | None, hold: BookingHold) -> bool:
    return (
        slot is not None
        and slot.id == hold.slot_id
        and slot.status == "held"
    )


def count_stale_exclusive_holds(db: Session, moment: datetime | None = None) -> dict[str, int]:
    """Read-only inventory of holds that V0 expire would cancel (test/staging assessment)."""
    moment = moment or now()
    rows = (
        db.query(BookingHold, Booking)
        .join(Booking, Booking.id == BookingHold.booking_id)
        .filter(BookingHold.status == "active")
        .all()
    )
    by_status: dict[str, int] = {}
    total = 0
    for hold, booking in rows:
        if aware(hold.expires_at) > moment:
            continue
        if booking.status not in EXCLUSIVE_BOOKING_STATUSES:
            continue
        by_status[booking.status] = by_status.get(booking.status, 0) + 1
        total += 1
    return {"total": total, "by_status": by_status}


def _cancel_exclusive_booking(db: Session, booking: Booking) -> None:
    if booking.status not in EXCLUSIVE_BOOKING_STATUSES:
        return
    # Local transition avoids circular import with routers.deals.
    booking.status = "Cancelled"
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    if req and req.status != "Cancelled":
        req.status = "Cancelled"
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    if conv:
        db.add(
            Message(
                conversation_id=conv.id,
                kind="system",
                body="Удержание даты истекло. Слот снова свободен.",
            )
        )


def expire_holds(db: Session) -> int:
    """Atomically expire due holds. Lock order: Booking → BookingHold → AvailabilitySlot."""
    moment = now()
    candidates = (
        db.query(BookingHold.id)
        .filter(BookingHold.status == "active")
        .order_by(BookingHold.id)
        .all()
    )
    expired = 0
    for (hold_id,) in candidates:
        hold_probe = db.get(BookingHold, hold_id)
        if hold_probe is None or hold_probe.status != "active":
            continue
        if aware(hold_probe.expires_at) > moment:
            continue

        booking = (
            db.query(Booking)
            .filter(Booking.id == hold_probe.booking_id)
            .with_for_update()
            .one_or_none()
        )
        hold = (
            db.query(BookingHold)
            .filter(BookingHold.id == hold_id)
            .with_for_update()
            .one_or_none()
        )
        if hold is None or hold.status != "active" or aware(hold.expires_at) > moment:
            continue

        slot = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.id == hold.slot_id)
            .with_for_update()
            .one_or_none()
        )

        hold.status = "expired"
        cancelled = False
        slot_opened = False

        if booking and booking.status in EXCLUSIVE_BOOKING_STATUSES:
            _cancel_exclusive_booking(db, booking)
            cancelled = True
            if slot_owned_by_hold(slot, hold):
                slot.status = "open"
                slot_opened = True
        elif booking and booking.status == "Confirmed":
            # Stale active hold after confirm: never reopen a confirmed slot.
            pass
        else:
            # Orphan / non-exclusive: free held slot only when this hold still owns it
            # and no other active hold claims the same slot.
            if slot_owned_by_hold(slot, hold):
                other = (
                    db.query(BookingHold)
                    .filter(
                        BookingHold.slot_id == hold.slot_id,
                        BookingHold.status == "active",
                        BookingHold.id != hold.id,
                    )
                    .first()
                )
                if other is None:
                    slot.status = "open"
                    slot_opened = True

        expired += 1
        audit(
            db,
            actor_user_id=None,
            action="hold.expired",
            entity_type="booking",
            entity_id=hold.booking_id,
            payload={
                "hold_id": hold.id,
                "slot_id": hold.slot_id,
                "booking_status": booking.status if booking else None,
                "cancelled": cancelled,
                "slot_opened": slot_opened,
            },
        )
    return expired


def consume_hold_on_confirm(db: Session, hold: BookingHold, *, booking_id: str) -> None:
    """End hold after successful confirm without calling it a TTL expiry."""
    hold.status = "cancelled"
    audit(
        db,
        actor_user_id=None,
        action="hold.consumed",
        entity_type="booking",
        entity_id=booking_id,
        payload={"hold_id": hold.id, "slot_id": hold.slot_id, "reason": "advance_confirmed"},
    )
