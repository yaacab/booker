"""Event-day replacement: cancelled role → catalog search with excludes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.models import Artist, Booking, Event, EventTeamRequirement, Offer, Request, Venue
from booker_api.security import aware, now

CLOSED_REQUEST_STATUSES = frozenset({"Confirmed", "Completed"})
CANCELLED_REQUEST_STATUSES = frozenset({"Cancelled", "Declined", "Expired"})


def qty_of(n: int | None) -> int:
    if not n or n < 1:
        return 1
    return min(20, int(n))


def is_closed_request(req: Request, booking: Booking | None) -> bool:
    if req.status in CLOSED_REQUEST_STATUSES:
        return True
    return bool(booking and booking.status in {"Confirmed", "InProgress", "Completed"})


def requests_for_requirement(db: Session, event_id: str, requirement_id: str) -> list[Request]:
    return (
        db.query(Request)
        .filter(Request.event_id == event_id, Request.requirement_id == requirement_id)
        .order_by(Request.created_at.asc())
        .all()
    )


def booking_for_request(db: Session, req: Request) -> Booking | None:
    offer = db.query(Offer).filter(Offer.request_id == req.id).one_or_none()
    if not offer:
        return None
    return db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()


def filled_count(db: Session, reqs: list[Request]) -> int:
    closed = 0
    for req in reqs:
        if is_closed_request(req, booking_for_request(db, req)):
            closed += 1
    return closed


def cancelled_requests_payload(db: Session, reqs: list[Request]) -> list[dict]:
    items = []
    for req in reqs:
        if req.status not in CANCELLED_REQUEST_STATUSES:
            booking = booking_for_request(db, req)
            if not booking or booking.status != "Cancelled":
                continue
        booking = booking_for_request(db, req)
        name = None
        if req.resource_type == "artist":
            artist = db.get(Artist, req.resource_id)
            name = artist.name if artist else None
        elif req.resource_type == "venue":
            venue = db.get(Venue, req.resource_id)
            name = venue.name if venue else None
        items.append(
            {
                "id": req.id,
                "status": req.status,
                "resource_type": req.resource_type,
                "resource_id": req.resource_id,
                "resource_name": name,
                "booking_id": booking.id if booking else None,
                "booking_status": booking.status if booking else None,
            }
        )
    return items


def exclude_resource_ids(db: Session, reqs: list[Request]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for req in reqs:
        if req.resource_id in seen:
            continue
        seen.add(req.resource_id)
        out.append(req.resource_id)
    return out


def build_replacement_plan(
    db: Session,
    event: Event,
    requirement: EventTeamRequirement,
) -> dict:
    reqs = requests_for_requirement(db, event.id, requirement.id)
    need = qty_of(requirement.qty)
    filled = filled_count(db, reqs)
    open_slots = max(0, need - filled)
    cancelled = cancelled_requests_payload(db, reqs)
    exclude = exclude_resource_ids(db, reqs)
    event_day = aware(event.event_date).date().isoformat()
    return {
        "requirement_id": requirement.id,
        "category_code": requirement.category_code,
        "role_label": requirement.role_label or "",
        "qty": need,
        "filled": filled,
        "open_slots": open_slots,
        "needs_replacement": open_slots > 0 and len(cancelled) > 0,
        "cancelled_requests": cancelled,
        "exclude_resource_ids": exclude,
        "search": {
            "date": event_day,
            "category": requirement.category_code,
            "city": event.city,
            "event_id": event.id,
            "requirement_id": requirement.id,
            "exclude": ",".join(exclude) if exclude else "",
        },
        "generated_at": now().isoformat(),
    }
