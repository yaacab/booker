import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.requests import Request as HttpRequest

from booker_api.calendar import overlapping_slots
from booker_api.composition import ensure_requirements, replace_requirements, requirement_payload
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_day import (
    build_day_status,
    check_in_booking,
    check_in_event,
    check_out_booking,
    check_out_event,
)
from booker_api.file_scan import scan_upload
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    BookingHold,
    Contract,
    Conversation,
    DealAttachment,
    Dispute,
    Event,
    EventTeamRequirement,
    Message,
    Offer,
    OfferVersion,
    Organization,
    Payment,
    Request,
    TeamMember,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.notifications import on_offer_created, on_request_created
from booker_api.pricing import first_deal_waive, price_breakdown
from booker_api.rate_limit import client_key, messaging_limiter, upload_limiter
from booker_api.replacement import build_replacement_plan
from booker_api.schemas import DISPUTE_CATEGORIES
from booker_api.security import (
    audit,
    authenticate_token,
    aware,
    current_user,
    hold_deadline,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["deals"])


def _open_slot_for_request(db: Session, req: Request) -> AvailabilitySlot | None:
    if req.resource_type == "artist":
        return (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "artist",
                AvailabilitySlot.resource_id == req.resource_id,
                AvailabilitySlot.status == "open",
            )
            .first()
        )
    if req.resource_type == "hall":
        return (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "hall",
                AvailabilitySlot.resource_id == req.resource_id,
                AvailabilitySlot.status == "open",
            )
            .first()
        )
    if req.resource_type == "venue":
        halls = db.query(VenueHall).filter(VenueHall.venue_id == req.resource_id).all()
        for hall in halls:
            slot = (
                db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.resource_type == "hall",
                    AvailabilitySlot.resource_id == hall.id,
                    AvailabilitySlot.status == "open",
                )
                .first()
            )
            if slot:
                return slot
    return None


def _honorarium_for_request(db: Session, req: Request) -> int:
    if req.resource_type == "artist":
        tariff = db.query(ArtistTariff).filter(ArtistTariff.artist_id == req.resource_id).first()
        return tariff.honorarium_rub if tariff else 100000
    if req.resource_type in {"venue", "hall"}:
        venue_id = req.resource_id
        if req.resource_type == "hall":
            hall = db.get(VenueHall, req.resource_id)
            venue_id = hall.venue_id if hall else req.resource_id
        tariff = db.query(VenueTariff).filter(VenueTariff.venue_id == venue_id).first()
        return tariff.honorarium_rub if tariff else 220000
    return 100000

ALLOWED = {
    "Draft": {"RequestSent"},
    "RequestSent": {"Negotiation", "Cancelled"},
    "Negotiation": {"DateHeld", "Cancelled"},
    "DateHeld": {"AwaitingContract", "Cancelled"},
    "AwaitingContract": {"AwaitingPayment", "Cancelled"},
    "AwaitingPayment": {"Confirmed", "Cancelled"},
    "Confirmed": {"InProgress", "Cancelled", "Dispute"},
    "InProgress": {"Completed", "Dispute"},
    "Dispute": {"Resolved"},
}


def _transition(booking: Booking, to: str) -> None:
    allowed = ALLOWED.get(booking.status, set())
    if to not in allowed and to != booking.status:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Нельзя {booking.status} → {to}")
    booking.status = to


def expire_holds(db: Session) -> int:
    expired = 0
    holds = db.query(BookingHold).filter(BookingHold.status == "active").all()
    moment = now()
    for hold in holds:
        if aware(hold.expires_at) > moment:
            continue
        hold.status = "expired"
        slot = db.get(AvailabilitySlot, hold.slot_id)
        booking = db.get(Booking, hold.booking_id)
        if slot and slot.status == "held":
            slot.status = "open"
        if booking and booking.status == "DateHeld":
            _transition(booking, "Cancelled")
            offer = db.get(Offer, booking.offer_id)
            req = db.get(Request, offer.request_id) if offer else None
            if req:
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
        expired += 1
        audit(
            db,
            actor_user_id=None,
            action="hold.expired",
            entity_type="booking",
            entity_id=hold.booking_id,
        )
    return expired


@router.post("/events")
def create_event(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_id = body.get("organization_id")
    title = body.get("title")
    event_date = body.get("event_date")
    if not organization_id or not title or not event_date:
        raise HTTPException(400, "organization_id, title и event_date обязательны")
    require_org_writer(db, user, organization_id)
    event = Event(
        organization_id=organization_id,
        title=title,
        city=body.get("city", "Москва"),
        event_date=datetime.fromisoformat(event_date)
        if isinstance(event_date, str)
        else event_date,
        guest_count=body.get("guest_count", 50),
        budget_rub=body.get("budget_rub"),
        notes=body.get("notes", ""),
        status="Draft",
    )
    db.add(event)
    db.flush()
    requirements = []
    if settings.composition_v2:
        explicit = body.get("requirements")
        requirements = ensure_requirements(
            db, event, explicit if isinstance(explicit, list) else None, actor_user_id=user.id
        )
    db.commit()
    db.refresh(event)
    return {"id": event.id, "status": event.status, "requirements": requirements}


def _org_ids(db: Session, user: User) -> list[str]:
    return [
        m.organization_id
        for m in db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    ]


@router.get("/events")
def list_events(
    organization_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ids = _org_ids(db, user)
    if organization_id:
        require_org_member(db, user, organization_id)
        ids = [organization_id]
    rows = db.query(Event).filter(Event.organization_id.in_(ids)).all() if ids else []
    return {
        "items": [
            {
                "id": e.id,
                "title": e.title,
                "status": e.status,
                "event_date": e.event_date.isoformat(),
                "city": e.city,
                "organization_id": e.organization_id,
            }
            for e in rows
        ]
    }


@router.get("/events/{event_id}")
def get_event(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_member(db, user, event.organization_id)
    requirements = (
        ensure_requirements(db, event, actor_user_id=user.id) if settings.composition_v2 else []
    )
    requests = []
    for req in db.query(Request).filter(Request.event_id == event.id).all():
        offer = db.query(Offer).filter(Offer.request_id == req.id).one_or_none()
        booking = None
        quote_id = None
        if offer:
            booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()
            if offer.active_version_id:
                version = db.get(OfferVersion, offer.active_version_id)
                if version:
                    quote_id = version.id
        item = {
            "id": req.id,
            "status": req.status,
            "resource_type": req.resource_type,
            "resource_id": req.resource_id,
            "requirement_id": getattr(req, "requirement_id", None),
            "booking_id": booking.id if booking else None,
        }
        if quote_id:
            item["quote_id"] = quote_id
        requests.append(item)
    db.commit()
    return {
        "id": event.id,
        "title": event.title,
        "status": event.status,
        "city": event.city,
        "event_date": event.event_date.isoformat(),
        "guest_count": event.guest_count,
        "notes": event.notes,
        "organization_id": event.organization_id,
        "requirements": requirements,
        "requests": requests,
    }


@router.get("/events/{event_id}/offline-pack")
def event_offline_pack(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Сводка для дня события: печать / офлайн у concierge."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_member(db, user, event.organization_id)
    requirements = ensure_requirements(db, event, actor_user_id=user.id) if settings.composition_v2 else []
    reqs = db.query(Request).filter(Request.event_id == event.id).all()
    pack_requests = []
    for req in reqs:
        offer = db.query(Offer).filter(Offer.request_id == req.id).one_or_none()
        booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none() if offer else None
        pack_requests.append(
            {
                "id": req.id,
                "status": req.status,
                "resource_type": req.resource_type,
                "requirement_id": getattr(req, "requirement_id", None),
                "booking_id": booking.id if booking else None,
                "booking_status": booking.status if booking else None,
            }
        )
    db.commit()
    audit(
        db,
        actor_user_id=user.id,
        action="event.offline_pack",
        entity_type="event",
        entity_id=event.id,
    )
    db.commit()
    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "status": event.status,
            "city": event.city,
            "event_date": event.event_date.isoformat(),
            "guest_count": event.guest_count,
        },
        "requirements": requirements,
        "requests": pack_requests,
        "generated_at": now().isoformat(),
    }


@router.get("/events/{event_id}/day-status")
def event_day_status(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_member(db, user, event.organization_id)
    return build_day_status(db, event)


@router.post("/events/{event_id}/check-in")
def event_check_in(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    try:
        result = check_in_event(db, event)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit(
        db,
        actor_user_id=user.id,
        action="event.check_in",
        entity_type="event",
        entity_id=event.id,
        payload={"bookings": result["checked_in_bookings"]},
    )
    db.commit()
    return {**result, "day_status": build_day_status(db, event)}


@router.post("/events/{event_id}/check-out")
def event_check_out(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    try:
        result = check_out_event(db, event)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit(
        db,
        actor_user_id=user.id,
        action="event.check_out",
        entity_type="event",
        entity_id=event.id,
        payload={"bookings": result["checked_out_bookings"]},
    )
    db.commit()
    return {**result, "day_status": build_day_status(db, event)}


@router.post("/bookings/{booking_id}/check-in")
def booking_check_in(booking_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = db.get(Event, booking.event_id)
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    if not event or not req:
        raise HTTPException(404, "Сделка не найдена")
    if not (
        membership_ok(db, user, event.organization_id)
        or membership_ok(db, user, req.supplier_org_id)
    ):
        raise HTTPException(403, "Нет доступа")
    try:
        status = check_in_booking(booking)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if event.status in {"Confirmed", "Planning", "Draft", "RequestSent", "Negotiation"}:
        event.status = "InProgress"
    audit(
        db,
        actor_user_id=user.id,
        action="booking.check_in",
        entity_type="booking",
        entity_id=booking.id,
    )
    db.commit()
    return {"booking_id": booking.id, "status": status, "event_status": event.status}


@router.post("/bookings/{booking_id}/check-out")
def booking_check_out(booking_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = db.get(Event, booking.event_id)
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    if not event or not req:
        raise HTTPException(404, "Сделка не найдена")
    if not (
        membership_ok(db, user, event.organization_id)
        or membership_ok(db, user, req.supplier_org_id)
    ):
        raise HTTPException(403, "Нет доступа")
    try:
        status = check_out_booking(booking)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    day = build_day_status(db, event)
    if day["summary"]["in_progress"] == 0 and day["summary"]["confirmed"] == 0 and day["summary"]["completed"] > 0:
        event.status = "Completed"
    audit(
        db,
        actor_user_id=user.id,
        action="booking.check_out",
        entity_type="booking",
        entity_id=booking.id,
    )
    db.commit()
    return {"booking_id": booking.id, "status": status, "event_status": event.status}


@router.get("/events/{event_id}/requirements/{requirement_id}/replacement")
def requirement_replacement_plan(
    event_id: str,
    requirement_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_member(db, user, event.organization_id)
    requirement = db.get(EventTeamRequirement, requirement_id)
    if not requirement or requirement.event_id != event.id:
        raise HTTPException(404, "Позиция состава не найдена")
    plan = build_replacement_plan(db, event, requirement)
    audit(
        db,
        actor_user_id=user.id,
        action="replacement.viewed",
        entity_type="requirement",
        entity_id=requirement.id,
        payload={"open_slots": plan["open_slots"], "cancelled": len(plan["cancelled_requests"])},
    )
    db.commit()
    return plan


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: str,
    body: dict | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    expire_holds(db)
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    event = db.get(Event, booking.event_id)
    if not req or not event:
        raise HTTPException(404, "Бронь не найдена")
    cust_org = event.organization_id
    sup_org = req.supplier_org_id
    if membership_ok(db, user, cust_org):
        require_org_writer(db, user, cust_org)
    elif membership_ok(db, user, sup_org):
        require_org_writer(db, user, sup_org)
    else:
        raise HTTPException(403, "Нет доступа")
    if booking.status in {"Cancelled", "Completed"}:
        raise HTTPException(409, "Бронь уже закрыта")
    _transition(booking, "Cancelled")
    req.status = "Cancelled"
    slot = db.get(AvailabilitySlot, booking.slot_id)
    if slot and slot.status in {"held", "confirmed"}:
        slot.status = "open"
    hold = (
        db.query(BookingHold)
        .filter(BookingHold.booking_id == booking.id, BookingHold.status == "active")
        .one_or_none()
    )
    if hold:
        hold.status = "cancelled"
    reason = (body or {}).get("reason") if isinstance(body, dict) else None
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    if conv:
        text = "Сделка отменена."
        if reason:
            text = f"{text} Причина: {reason}"
        db.add(Message(conversation_id=conv.id, kind="system", body=text))
    audit(
        db,
        actor_user_id=user.id,
        action="booking.cancelled",
        entity_type="booking",
        entity_id=booking.id,
        payload={"request_id": req.id, "reason": reason or ""},
    )
    db.commit()
    return {"booking_id": booking.id, "status": booking.status, "request_id": req.id, "request_status": req.status}


@router.put("/events/{event_id}/requirements")
def put_event_requirements(
    event_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    items = body.get("items") if isinstance(body.get("items"), list) else []
    rows = replace_requirements(db, event, items, actor_user_id=user.id)
    db.commit()
    return {"requirements": [requirement_payload(r) for r in rows]}


@router.get("/requests")
def list_requests(
    organization_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ids = _org_ids(db, user)
    if organization_id:
        require_org_member(db, user, organization_id)
        ids = [organization_id]
    rows = db.query(Request).filter(Request.supplier_org_id.in_(ids)).all() if ids else []
    items = []
    for req in rows:
        event = db.get(Event, req.event_id)
        offer = db.query(Offer).filter(Offer.request_id == req.id).one_or_none()
        booking = None
        if offer:
            booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()
        slot = _open_slot_for_request(db, req)
        honorarium = _honorarium_for_request(db, req)
        items.append(
            {
                "id": req.id,
                "status": req.status,
                "resource_type": req.resource_type,
                "resource_id": req.resource_id,
                "event_title": event.title if event else "",
                "event_date": event.event_date.isoformat() if event else None,
                "offer_id": offer.id if offer else None,
                "booking_id": booking.id if booking else None,
                "slot_id": slot.id if slot else None,
                "honorarium_rub": honorarium,
            }
        )
    return {"items": items}


@router.get("/bookings")
def list_bookings(
    organization_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ids = set(_org_ids(db, user))
    if organization_id:
        require_org_member(db, user, organization_id)
        ids = {organization_id}
    rows = db.query(Booking).all()
    items = []
    for booking in rows:
        offer = db.get(Offer, booking.offer_id)
        req = db.get(Request, offer.request_id) if offer else None
        event = db.get(Event, booking.event_id)
        if not req or not event:
            continue
        if event.organization_id not in ids and req.supplier_org_id not in ids:
            continue
        items.append(
            {
                "id": booking.id,
                "status": booking.status,
                "event_title": event.title,
                "event_date": event.event_date.isoformat(),
            }
        )
    return {"items": items}


@router.post("/quick-request")
def quick_request(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artist_id = body.get("artist_id")
    slot_id = body.get("slot_id")
    if not artist_id or not slot_id:
        raise HTTPException(400, "artist_id и slot_id обязательны")
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    slot = db.get(AvailabilitySlot, slot_id)
    if not slot or slot.status != "open":
        raise HTTPException(409, "Слот недоступен")
    if slot.resource_type != "artist" or slot.resource_id != artist.id:
        raise HTTPException(400, "Слот не относится к этому артисту")
    event_id = body.get("event_id")
    requirement_id = body.get("requirement_id")
    if event_id:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(404, "Событие не найдено")
        require_org_writer(db, user, event.organization_id)
        if requirement_id:
            need = db.get(EventTeamRequirement, requirement_id)
            if not need or need.event_id != event.id:
                raise HTTPException(400, "requirement_id не относится к этому событию")
    else:
        members = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
        customer_ids: list[str] = []
        writable_ids: list[str] = []
        for m in members:
            org = db.get(Organization, m.organization_id)
            if not org or org.kind != "customer":
                continue
            customer_ids.append(org.id)
            if user.is_platform_admin or m.role in {"owner", "admin", "manager"}:
                writable_ids.append(org.id)
        if not customer_ids:
            raise HTTPException(400, "Сначала создайте организацию заказчика")
        active_id = user.active_organization_id
        if active_id in writable_ids:
            customer_org_id = active_id
        elif writable_ids:
            customer_org_id = writable_ids[0]
        else:
            customer_org_id = active_id if active_id in customer_ids else customer_ids[0]
        require_org_writer(db, user, customer_org_id)
        event = Event(
            organization_id=customer_org_id,
            title=body.get("title") or f"Заявка: {artist.name}",
            city=artist.city,
            event_date=slot.starts_at,
            guest_count=int(body.get("guest_count") or 50),
            notes=body.get("notes") or "",
            status="Draft",
        )
        db.add(event)
        db.flush()
        requirement_id = None
    req = Request(
        event_id=event.id,
        resource_type="artist",
        resource_id=artist.id,
        supplier_org_id=artist.organization_id,
        status="RequestSent",
    )
    if hasattr(req, "requirement_id"):
        req.requirement_id = requirement_id
    event.status = "RequestSent"
    db.add(req)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="request.created",
        entity_type="request",
        entity_id=req.id,
    )
    on_request_created(
        db,
        actor_user_id=user.id,
        request_id=req.id,
        supplier_org_id=req.supplier_org_id,
        event_title=event.title,
    )
    db.commit()
    return {"event_id": event.id, "request_id": req.id, "status": req.status}


@router.post("/events/{event_id}/requests")
def create_request(
    event_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    resource_type = body["resource_type"]
    resource_id = body["resource_id"]
    if resource_type == "artist":
        artist = db.get(Artist, resource_id)
        if not artist:
            raise HTTPException(404, "Артист не найден")
        supplier_org_id = artist.organization_id
    else:
        venue = db.get(Venue, resource_id)
        if not venue:
            raise HTTPException(404, "Площадка не найдена")
        supplier_org_id = venue.organization_id
    requirement_id = body.get("requirement_id")
    if requirement_id:
        need = db.get(EventTeamRequirement, requirement_id)
        if not need or need.event_id != event.id:
            raise HTTPException(400, "requirement_id не относится к этому событию")
    req = Request(
        event_id=event.id,
        resource_type=resource_type,
        resource_id=resource_id,
        supplier_org_id=supplier_org_id,
        status="RequestSent",
    )
    if hasattr(req, "requirement_id"):
        req.requirement_id = requirement_id
    db.add(req)
    db.flush()
    event.status = "RequestSent"
    audit(
        db,
        actor_user_id=user.id,
        action="request.created",
        entity_type="request",
        entity_id=req.id,
    )
    on_request_created(
        db,
        actor_user_id=user.id,
        request_id=req.id,
        supplier_org_id=supplier_org_id,
        event_title=event.title,
    )
    db.commit()
    db.refresh(req)
    return {"id": req.id, "status": req.status}


@router.post("/requests/{request_id}/offers")
def create_offer(
    request_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    expire_holds(db)
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    member = require_org_writer(db, user, req.supplier_org_id)
    if not member.can_confirm_offer and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет права подтверждать оффер")
    raw_honorarium = body.get("honorarium_rub")
    if raw_honorarium is None:
        raise HTTPException(400, "honorarium_rub обязателен")
    try:
        honorarium = int(raw_honorarium)
    except (TypeError, ValueError):
        raise HTTPException(400, "honorarium_rub должен быть числом") from None
    if honorarium <= 0:
        raise HTTPException(400, "honorarium_rub должен быть больше нуля")
    event = db.get(Event, req.event_id)
    waive = bool(event and first_deal_waive(db, event.organization_id))
    breakdown = price_breakdown(honorarium, waive_commission=waive)
    slot_id = body.get("slot_id")
    if not slot_id:
        raise HTTPException(400, "slot_id обязателен")
    slot = db.get(AvailabilitySlot, slot_id)
    if not slot:
        raise HTTPException(404, "Слот не найден")
    if slot.resource_type != req.resource_type or slot.resource_id != req.resource_id:
        raise HTTPException(400, "Слот не относится к ресурсу заявки")
    offer = Offer(request_id=req.id)
    db.add(offer)
    db.flush()
    version = OfferVersion(
        offer_id=offer.id,
        honorarium_rub=breakdown["honorarium_rub"],
        commission_rate=breakdown["commission_rate"],
        commission_rub=breakdown["commission_rub"],
        total_rub=breakdown["total_rub"],
        terms=body.get("terms", ""),
    )
    db.add(version)
    db.flush()
    offer.active_version_id = version.id
    req.status = "Negotiation"
    booking = Booking(
        event_id=req.event_id,
        offer_id=offer.id,
        slot_id=slot.id,
        status="Negotiation",
    )
    db.add(booking)
    db.flush()
    conv = Conversation(booking_id=booking.id)
    db.add(conv)
    db.flush()
    db.add(
        Message(
            conversation_id=conv.id,
            kind="system",
            body="Создано предложение. Цена считается только на сервере.",
        )
    )
    if event:
        event.status = "Negotiation"
    audit(
        db,
        actor_user_id=user.id,
        action="offer.created",
        entity_type="offer",
        entity_id=offer.id,
        payload=breakdown,
    )
    if event:
        on_offer_created(
            db,
            actor_user_id=user.id,
            offer_id=offer.id,
            customer_org_id=event.organization_id,
            event_title=event.title,
        )
    db.commit()
    db.refresh(offer)
    db.refresh(version)
    db.refresh(booking)
    return {
        "id": offer.id,
        "booking_id": booking.id,
        "version": {
            "id": version.id,
            "quote_id": version.id,
            **breakdown,
            "customer_ack": version.customer_ack,
            "supplier_ack": version.supplier_ack,
        },
    }


@router.post("/offers/{offer_id}/versions")
def new_version(
    offer_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Оффер не найден")
    req = db.get(Request, offer.request_id)
    event = db.get(Event, req.event_id)
    if membership_ok(db, user, req.supplier_org_id):
        require_org_writer(db, user, req.supplier_org_id)
    elif event and membership_ok(db, user, event.organization_id):
        require_org_writer(db, user, event.organization_id)
    else:
        raise HTTPException(403, "Нет доступа")
    raw_honorarium = body.get("honorarium_rub")
    if raw_honorarium is None:
        raise HTTPException(400, "honorarium_rub обязателен")
    try:
        honorarium = int(raw_honorarium)
    except (TypeError, ValueError):
        raise HTTPException(400, "honorarium_rub должен быть числом") from None
    if honorarium <= 0:
        raise HTTPException(400, "honorarium_rub должен быть больше нуля")
    booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()
    if booking and booking.status in {"AwaitingPayment", "Confirmed", "InProgress", "Completed"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Менять цену после перехода к оплате нельзя",
        )
    waive = bool(
        event
        and first_deal_waive(db, event.organization_id, exclude_booking_id=booking.id if booking else None)
    )
    breakdown = price_breakdown(honorarium, waive_commission=waive)
    version = OfferVersion(
        offer_id=offer.id,
        honorarium_rub=breakdown["honorarium_rub"],
        commission_rate=breakdown["commission_rate"],
        commission_rub=breakdown["commission_rub"],
        total_rub=breakdown["total_rub"],
        terms=body.get("terms", ""),
        customer_ack=False,
        supplier_ack=False,
    )
    db.add(version)
    db.flush()
    offer.active_version_id = version.id
    audit(
        db,
        actor_user_id=user.id,
        action="offer.version",
        entity_type="offer_version",
        entity_id=version.id,
        payload=breakdown,
    )
    db.commit()
    return {"id": version.id, "quote_id": version.id, **breakdown, "active": False}


def membership_ok(db, user, org_id) -> bool:
    from booker_api.security import membership

    return bool(membership(db, user.id, org_id) or user.is_platform_admin)


@router.post("/offers/{offer_id}/ack")
def ack_offer(
    offer_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    offer = db.get(Offer, offer_id)
    if not offer or not offer.active_version_id:
        raise HTTPException(404, "Оффер не найден")
    version = db.get(OfferVersion, offer.active_version_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, req.event_id)
    quote_id = body.get("quote_id")
    if quote_id is not None and quote_id != version.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "quote_id устарел: подтверждается только активная версия предложения",
        )
    side = body.get("side")
    if side not in {"supplier", "customer"}:
        raise HTTPException(400, "side: customer|supplier")
    if side == "supplier":
        member = require_org_writer(db, user, req.supplier_org_id)
        if not member.can_confirm_offer:
            raise HTTPException(403, "Нет права подтверждать оффер")
        version.supplier_ack = True
    elif side == "customer":
        require_org_writer(db, user, event.organization_id)
        version.customer_ack = True
    else:
        raise HTTPException(400, "side: customer|supplier")
    both = version.customer_ack and version.supplier_ack
    audit(
        db,
        actor_user_id=user.id,
        action="offer.ack",
        entity_type="offer_version",
        entity_id=version.id,
        payload={"side": side, "both": both},
    )
    db.commit()
    return {
        "quote_id": version.id,
        "honorarium_rub": version.honorarium_rub,
        "commission_rate": version.commission_rate,
        "commission_rub": version.commission_rub,
        "total_rub": version.total_rub,
        "customer_ack": version.customer_ack,
        "supplier_ack": version.supplier_ack,
        "active": both,
    }


@router.post("/bookings/{booking_id}/hold")
def hold_booking(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    expire_holds(db)
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if user.is_platform_admin:
        pass
    elif membership_ok(db, user, cust_org):
        require_org_writer(db, user, cust_org)
    elif membership_ok(db, user, sup_org):
        require_org_member(db, user, sup_org)
    else:
        raise HTTPException(403, "Нет доступа")
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id) if offer else None
    if not version or not (version.customer_ack and version.supplier_ack):
        raise HTTPException(409, "Оффер не подтверждён обеими сторонами")
    slot = db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == booking.slot_id).with_for_update()
    ).scalar_one()
    busy = overlapping_slots(
        db,
        slot.resource_type,
        slot.resource_id,
        slot.starts_at,
        slot.ends_at,
        statuses=("held", "confirmed", "busy"),
        exclude_id=slot.id,
    )
    if slot.status in {"held", "confirmed", "busy"} or busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "Слот уже удерживается или подтверждён")
    claimed = db.execute(
        update(AvailabilitySlot)
        .where(AvailabilitySlot.id == slot.id, AvailabilitySlot.status == "open")
        .values(status="held")
    )
    if claimed.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Слот уже удерживается или подтверждён")
    db.refresh(slot)
    hold = BookingHold(
        booking_id=booking.id,
        slot_id=slot.id,
        expires_at=hold_deadline(),
        status="active",
    )
    db.add(hold)
    _transition(booking, "DateHeld")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    db.add(Message(conversation_id=conv.id, kind="system", body="Дата удерживается до оплаты."))
    audit(
        db,
        actor_user_id=user.id,
        action="hold.created",
        entity_type="booking",
        entity_id=booking.id,
    )
    db.commit()
    db.refresh(hold)
    return {"hold_id": hold.id, "expires_at": hold.expires_at.isoformat(), "status": booking.status}


@router.post("/holds/expire")
def run_expire(request: HttpRequest, db: Session = Depends(get_db)):
    internal = request.headers.get("x-internal-token", "")
    if not (internal and hmac.compare_digest(internal, settings.webhook_secret)):
        auth = request.headers.get("authorization") or ""
        raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        user = None
        if raw:
            user, _session = authenticate_token(db, raw)
        if not user or not user.is_platform_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Только администратор платформы")
    count = expire_holds(db)
    db.commit()
    return {"expired": count}


def _booking_participant_orgs(db: Session, booking: Booking) -> tuple[str, str]:
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    return event.organization_id, req.supplier_org_id


@router.post("/bookings/{booking_id}/attachments")
async def upload_booking_attachment(
    booking_id: str,
    request: HttpRequest,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    upload_limiter.check(client_key(request, "upload"))
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл слишком большой")
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")
    if user.is_platform_admin:
        pass
    elif membership_ok(db, user, cust_org):
        require_org_writer(db, user, cust_org)
    else:
        require_org_writer(db, user, sup_org)
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл слишком большой")
    safe_name = scan_upload(raw, file.filename or "file.bin", max_bytes=settings.max_upload_bytes)
    digest = hashlib.sha256(raw).hexdigest()
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    booking_dir = root / booking_id
    booking_dir.mkdir(parents=True, exist_ok=True)
    storage_key = f"{booking_id}/{digest[:16]}_{safe_name}"
    path = root / storage_key
    path.write_bytes(raw)
    row = DealAttachment(
        booking_id=booking_id,
        filename=safe_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(raw),
        sha256=digest,
        storage_key=storage_key,
        uploaded_by_user_id=user.id,
    )
    db.add(row)
    audit(
        db,
        actor_user_id=user.id,
        action="attachment.uploaded",
        entity_type="booking",
        entity_id=booking_id,
        payload={"attachment_id": row.id, "filename": safe_name, "sha256": digest},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
    }


def _deal_documents(
    version: OfferVersion,
    contract: Contract | None,
    attachments: list[DealAttachment] | None = None,
) -> list[dict]:
    docs = [
        {
            "kind": "offer",
            "id": version.id,
            "label": "Предложение",
            "quote_id": version.id,
            "signed": version.customer_ack and version.supplier_ack,
        }
    ]
    if contract:
        docs.append(
            {
                "kind": "contract",
                "id": contract.id,
                "label": "Договор",
                "signed": contract.customer_signed and contract.supplier_signed,
            }
        )
    for att in attachments or []:
        docs.append(
            {
                "kind": "attachment",
                "id": att.id,
                "label": att.filename,
                "signed": False,
                "size_bytes": att.size_bytes,
            }
        )
    return docs


@router.get("/deal-room/{booking_id}")
def deal_room(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    if not (
        membership_ok(db, user, event.organization_id)
        or membership_ok(db, user, req.supplier_org_id)
    ):
        raise HTTPException(403, "Нет доступа")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    version = db.get(OfferVersion, offer.active_version_id)
    contract = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    payment = db.query(Payment).filter(Payment.booking_id == booking.id).one_or_none()
    attachments = (
        db.query(DealAttachment)
        .filter(DealAttachment.booking_id == booking.id)
        .order_by(DealAttachment.created_at.asc())
        .all()
    )
    hold = (
        db.query(BookingHold)
        .filter(BookingHold.booking_id == booking.id, BookingHold.status == "active")
        .one_or_none()
    )
    cust_org = db.get(Organization, event.organization_id)
    sup_org = db.get(Organization, req.supplier_org_id)
    role = "customer" if membership_ok(db, user, event.organization_id) else "supplier"
    workspace_kind = "customer" if role == "customer" else (sup_org.kind if sup_org else "artist")
    return {
        "booking_id": booking.id,
        "offer_id": offer.id,
        "event_id": event.id,
        "requirement_id": getattr(req, "requirement_id", None),
        "status": booking.status,
        "role": role,
        "workspace_kind": workspace_kind,
        "event_title": event.title,
        "tabs": ["chat", "terms", "documents", "payments", "dispute"],
        "dispute_categories": [
            {"id": "no_show", "label": "Неявка"},
            {"id": "delay", "label": "Опоздание"},
            {"id": "quality", "label": "Качество услуги"},
            {"id": "payment", "label": "Платёж"},
            {"id": "cancel", "label": "Отмена"},
        ],
        "next_step": _next_step(booking.status),
        "participants": [
            {"role": "customer", "name": cust_org.name if cust_org else "Заказчик", "duty": "оплата и условия"},
            {"role": "supplier", "name": sup_org.name if sup_org else "Исполнитель", "duty": "дата и услуга"},
            {"role": "platform", "name": "Букер", "duty": "журнал и агрегатор, не исполнитель"},
        ],
        "hold": None
        if not hold
        else {"status": hold.status, "expires_at": hold.expires_at.isoformat()},
        "contract": None
        if not contract
        else {
            "id": contract.id,
            "customer_signed": contract.customer_signed,
            "supplier_signed": contract.supplier_signed,
            "body": contract.body,
            "otp_customer": contract.otp_customer,
            "otp_supplier": contract.otp_supplier,
        },
        "documents": _deal_documents(version, contract, attachments),
        "payment": None
        if not payment
        else {"id": payment.id, "status": payment.status, "amount_rub": payment.amount_rub},
        "quote": {
            "quote_id": version.id,
            "honorarium_rub": version.honorarium_rub,
            "commission_rate": version.commission_rate,
            "commission_rub": version.commission_rub,
            "total_rub": version.total_rub,
            "currency": version.currency,
            "customer_ack": version.customer_ack,
            "supplier_ack": version.supplier_ack,
            "source": (
                "Первая сделка: комиссия платформы 0. Гонорар как есть."
                if version.commission_rub == 0
                else "Предложение сформировано сервером"
            ),
        },
        "messages": [
            {
                "id": m.id,
                "kind": m.kind,
                "body": m.body,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


def _next_step(st: str) -> str:
    return {
        "Negotiation": "Подтвердить условия обеими сторонами",
        "DateHeld": "Подписать договор",
        "AwaitingContract": "Подписать договор",
        "AwaitingPayment": "Внести предоплату",
        "Confirmed": "Дождаться дня события",
    }.get(st, "Открыть помощь")


@router.post("/bookings/{booking_id}/disputes")
def open_booking_dispute(
    booking_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    if not (
        membership_ok(db, user, event.organization_id)
        or membership_ok(db, user, req.supplier_org_id)
    ):
        raise HTTPException(403, "Нет доступа")
    category = str(body.get("category") or "")
    if category not in DISPUTE_CATEGORIES:
        raise HTTPException(400, "Выберите категорию спора из списка")
    if booking.status not in {"Confirmed", "InProgress"}:
        raise HTTPException(409, "Спор открывается после подтверждённой брони")
    _transition(booking, "Dispute")
    dispute = Dispute(
        booking_id=booking.id,
        category=category,
        body=str(body.get("notes") or ""),
    )
    db.add(dispute)
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    if conv:
        db.add(
            Message(
                conversation_id=conv.id,
                kind="system",
                body="Открыт спор. Решение принимает оператор, не ИИ.",
            )
        )
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.opened",
        entity_type="dispute",
        entity_id=booking.id,
        payload={"category": category, "ai_decides": False},
    )
    db.commit()
    db.refresh(dispute)
    return {"id": dispute.id, "status": dispute.status, "ai_decides": False}


@router.post("/deal-room/{booking_id}/messages")
def post_message(
    booking_id: str,
    body: dict,
    request: HttpRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    messaging_limiter.check(client_key(request, "message"))
    conv = db.query(Conversation).filter(Conversation.booking_id == booking_id).one_or_none()
    if not conv:
        raise HTTPException(404, "Deal Room не найден")
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")
    text = body.get("body")
    if not text or not str(text).strip():
        raise HTTPException(400, "body обязателен")
    msg = Message(
        conversation_id=conv.id,
        author_user_id=user.id,
        kind="chat",
        body=str(text),
    )
    db.add(msg)
    db.commit()
    return {"id": msg.id}


@router.get("/sse/bookings/{booking_id}")
def sse_status(
    booking_id: str,
    request: HttpRequest,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse

    raw = token
    if not raw:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    user, _session = authenticate_token(db, raw)
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")

    def gen():
        yield f"data: {json.dumps({'status': booking.status})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
