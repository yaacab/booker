"""Event-day check-in/out for Control Room."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.models import Artist, Booking, Event, Offer, Request, Venue
from booker_api.security import now

BOOKING_CHECKIN_FROM = frozenset({"Confirmed"})
BOOKING_CHECKOUT_FROM = frozenset({"InProgress"})

EVENT_CHECKIN_FROM = frozenset({"Confirmed", "Planning", "Draft", "RequestSent", "Negotiation"})
EVENT_CHECKOUT_FROM = frozenset({"InProgress"})


def resource_name(db: Session, req: Request) -> str | None:
    if req.resource_type == "artist":
        artist = db.get(Artist, req.resource_id)
        return artist.name if artist else None
    if req.resource_type == "venue":
        venue = db.get(Venue, req.resource_id)
        return venue.name if venue else None
    return None


def event_bookings(db: Session, event_id: str) -> list[tuple[Request, Booking | None]]:
    rows: list[tuple[Request, Booking | None]] = []
    for req in db.query(Request).filter(Request.event_id == event_id).all():
        offer = db.query(Offer).filter(Offer.request_id == req.id).one_or_none()
        booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none() if offer else None
        rows.append((req, booking))
    return rows


def build_day_status(db: Session, event: Event) -> dict:
    bookings_payload: list[dict] = []
    confirmed = in_progress = completed = 0
    for req, booking in event_bookings(db, event.id):
        if not booking:
            continue
        status = booking.status
        if status == "Confirmed":
            confirmed += 1
        elif status == "InProgress":
            in_progress += 1
        elif status == "Completed":
            completed += 1
        bookings_payload.append(
            {
                "request_id": req.id,
                "booking_id": booking.id,
                "requirement_id": getattr(req, "requirement_id", None),
                "resource_type": req.resource_type,
                "resource_id": req.resource_id,
                "resource_name": resource_name(db, req),
                "booking_status": status,
                "can_check_in": status in BOOKING_CHECKIN_FROM,
                "can_check_out": status in BOOKING_CHECKOUT_FROM,
            }
        )
    total_active = confirmed + in_progress + completed
    can_event_check_in = event.status in EVENT_CHECKIN_FROM and confirmed > 0
    can_event_check_out = event.status in EVENT_CHECKOUT_FROM and in_progress > 0
    return {
        "event_id": event.id,
        "event_status": event.status,
        "can_event_check_in": can_event_check_in,
        "can_event_check_out": can_event_check_out,
        "bookings": bookings_payload,
        "summary": {
            "confirmed": confirmed,
            "in_progress": in_progress,
            "completed": completed,
            "total": total_active,
        },
        "generated_at": now().isoformat(),
    }


def check_in_booking(booking: Booking) -> str:
    if booking.status not in BOOKING_CHECKIN_FROM:
        raise ValueError(f"Нельзя check-in из статуса {booking.status}")
    booking.status = "InProgress"
    return booking.status


def check_out_booking(booking: Booking) -> str:
    if booking.status not in BOOKING_CHECKOUT_FROM:
        raise ValueError(f"Нельзя check-out из статуса {booking.status}")
    booking.status = "Completed"
    return booking.status


def check_in_event(db: Session, event: Event) -> dict:
    if event.status not in EVENT_CHECKIN_FROM:
        raise ValueError(f"Нельзя начать день события из статуса {event.status}")
    checked: list[str] = []
    for _req, booking in event_bookings(db, event.id):
        if booking and booking.status in BOOKING_CHECKIN_FROM:
            check_in_booking(booking)
            checked.append(booking.id)
    if not checked:
        raise ValueError("Нет подтверждённых сделок для check-in")
    event.status = "InProgress"
    return {"event_status": event.status, "checked_in_bookings": checked}


def check_out_event(db: Session, event: Event) -> dict:
    if event.status not in EVENT_CHECKOUT_FROM:
        raise ValueError(f"Нельзя завершить день события из статуса {event.status}")
    checked: list[str] = []
    for _req, booking in event_bookings(db, event.id):
        if booking and booking.status in BOOKING_CHECKOUT_FROM:
            check_out_booking(booking)
            checked.append(booking.id)
    if not checked:
        raise ValueError("Нет сделок в работе для check-out")
    # Keep InProgress while Confirmed (or leftover InProgress) bookings remain;
    # Completing the event with open deals breaks the authoritative lifecycle.
    remaining_active = [
        booking.id
        for _req, booking in event_bookings(db, event.id)
        if booking and booking.status in {"Confirmed", "InProgress"}
    ]
    if not remaining_active:
        event.status = "Completed"
    return {
        "event_status": event.status,
        "checked_out_bookings": checked,
        "remaining_active_bookings": remaining_active,
    }
