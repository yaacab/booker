"""Available replacements, rechecked against the event window and current lineup."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from booker_api.compatibility import assess_compatibility
from booker_api.event_budget import event_budget
from booker_api.matching import MatchingContext, selection_key
from booker_api.models import (
    Artist,
    Booking,
    Event,
    EventTeamRequirement,
    Offer,
    Request,
    Venue,
    VenueHall,
)
from booker_api.security import aware, now

CLOSED_REQUEST_STATUSES = frozenset({"Confirmed", "Completed"})
CANCELLED_REQUEST_STATUSES = frozenset({"Cancelled", "Declined", "Expired"})


def qty_of(n: int | None) -> int:
    if not n or n < 1:
        return 1
    return min(20, int(n))


def is_closed_request(req: Request, booking: Booking | None) -> bool:
    if booking:
        return booking.status in {"Confirmed", "InProgress", "Completed"}
    return req.status in CLOSED_REQUEST_STATUSES


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
        elif req.resource_type == "hall":
            hall = db.get(VenueHall, req.resource_id)
            venue = db.get(Venue, hall.venue_id) if hall else None
            name = f"{venue.name} · {hall.name}" if venue and hall else None
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
    event_day = aware(event.event_date).astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
    result = {
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

    result.update(replacement_candidates(db, event, requirement, result["needs_replacement"]))
    return result


def replacement_candidates(db, event, requirement, needed):
    base = {"candidates": [], "window": {"starts_at": aware(event.event_date).isoformat(),
        "ends_at": aware(event.ends_at).isoformat() if event.ends_at else None}}
    if event.status in {"Completed", "Cancelled"}:
        return {**base, "state": "closed", "needs_replacement": False}
    if not needed:
        return {**base, "state": "not_needed"}
    ctx = MatchingContext(db, event)
    if not ctx.window_known:
        return {**base, "state": "needs_window"}
    # A request already sent for any role must not be offered again as a new replacement.
    requests = db.query(Request).filter_by(event_id=event.id).all()
    excluded = {(r.resource_type, r.resource_id) for r in requests}
    actual = [line for line in event_budget(db, event)["lines"]
        if line["group"] == "confirmed" or line.get("reserved")]
    lineup = list(actual)
    for item in ctx.saved:
        if item.get("requirement_id") != requirement.id and selection_key(item) not in {selection_key(i) for i in lineup}:
            lineup.append(item)
    halls = []
    artists = []
    for item in lineup:
        if item["resource_type"] == "artist":
            artist = db.get(Artist, item["resource_id"])
            if artist:
                artists.append(artist)
        elif item.get("hall_id"):
            hall = db.get(VenueHall, item["hall_id"])
            venue = db.get(Venue, item["resource_id"])
            if hall and venue and hall.venue_id == venue.id:
                halls.append((venue, hall))
    occupied = {selection_key(i) for i in actual}

    def assess(artist, venue, hall):
        return assess_compatibility(db, artist=artist, venue=venue, hall=hall,
            starts_at=ctx.start, ends_at=ctx.end, guest_count=event.guest_count,
            event_city=event.city, own_slot_ids=ctx.own_slots)

    candidates = []
    for source in ctx.pool[requirement.category_code]:
        if selection_key(source) in occupied or (source["resource_type"], source["resource_id"]) in excluded or ("hall", source.get("hall_id")) in excluded:
            continue
        item = {**source, "reasons": list(source["reasons"]), "warnings": list(source["warnings"])}
        pairs = []
        if item["resource_type"] == "artist":
            artist = ctx.artists[item["resource_id"]]
            options = [assess(artist, venue, hall) for venue, hall in halls]
            fits = [p for p in options if p["status"] != "incompatible"]
            if options and not fits:
                continue
            if fits:
                pairs.append(min(fits, key=lambda p: (len(p["to_resolve"]), p["hall"]["id"])))
            else:
                item["warnings"].append("Площадка не выбрана: совместимость райдера не проверена")
        else:
            venue, hall = ctx.venues[item["resource_id"]], ctx.halls[item["hall_id"]]
            incompatible = False
            for artist in artists:
                options = [assess(artist, v, h) for v, h in [*halls, (venue, hall)]]
                fits = [p for p in options if p["status"] != "incompatible"]
                if not fits:
                    incompatible = True
                    break
                pairs.append(min(fits, key=lambda p: (len(p["to_resolve"]), p["hall"]["id"])))
            if incompatible:
                continue
            if not artists:
                item["warnings"].append("Артисты не выбраны: совместимость райдеров не проверена")
        if pairs:
            item["reasons"].append("Состав сопоставлен с залами: известных технических несоответствий нет")
            for pair in pairs:
                item["warnings"].extend(f"{c['label']}: {c['explanation']}" for c in pair["to_resolve"])
        item["warnings"] = list(dict.fromkeys(item["warnings"]))
        candidates.append(item)
    return {**base, "state": "available" if candidates else "empty",
        "candidates": sorted(candidates, key=lambda i: (i["name"].casefold(), i["candidate_key"]))}
