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
from booker_api.commerce.fees import SNAPSHOT_FIELDS, offer_fees, snapshot_payload
from booker_api.commerce.promotions import attribute_request
from booker_api.composition import ensure_requirements, replace_requirements, requirement_payload
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_commands import remember_command, replay_command
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
    AuditLog,
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
from booker_api.payments.adapter import payment_capabilities
from booker_api.rate_limit import analytics_limiter, client_key, messaging_limiter, upload_limiter
from booker_api.replacement import build_replacement_plan
from booker_api.schemas import DISPUTE_CATEGORIES, EventIn, RequestCreateIn
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


def _require_open_event(event: Event) -> None:
    if event.status in {"Completed", "Cancelled"}:
        raise HTTPException(409, "Событие закрыто. Для новых заявок создайте новое событие")


def _open_slot_for_request(db: Session, req: Request) -> AvailabilitySlot | None:
    from booker_api.compatibility import resource_available
    from booker_api.presentation import presentation_data

    event = db.get(Event, req.event_id)
    if not event or not event.ends_at or event.status in {"Completed", "Cancelled"}:
        return None
    start, end = aware(event.event_date), aware(event.ends_at)
    if start <= now() or end <= start:
        return None
    resources = [(req.resource_type, req.resource_id)]
    before = after = 0
    if req.resource_type == "venue":
        resources = [("hall", h.id) for h in db.query(VenueHall).filter_by(venue_id=req.resource_id).order_by(VenueHall.id)]
    if req.resource_type == "artist":
        artist = db.get(Artist, req.resource_id)
        technical = (presentation_data(db, artist)[1].get("technical") or {}) if artist else {}
        before, after = technical.get("setup_minutes") or 0, technical.get("teardown_minutes") or 0
    for kind, resource_id in resources:
        slots = db.query(AvailabilitySlot).filter_by(resource_type=kind, resource_id=resource_id).order_by(AvailabilitySlot.starts_at, AvailabilitySlot.id).all()
        blocked = [s for s in slots if s.status in {"busy", "held", "confirmed"}]
        for slot in slots:
            if slot.status == "open" and resource_available(db, kind, resource_id, start, end,
                    before=before, after=after, slots=[slot, *blocked]):
                return slot
    return None


def _slot_matches_request(db: Session, slot: AvailabilitySlot, req: Request) -> bool:
    """Artist/hall exact match; venue requests may use a hall slot of that venue."""
    if slot.resource_type == req.resource_type and slot.resource_id == req.resource_id:
        return True
    if req.resource_type == "venue" and slot.resource_type == "hall":
        hall = db.get(VenueHall, slot.resource_id)
        return bool(hall and hall.venue_id == req.resource_id)
    return False


def _validate_event_slot(db: Session, event: Event, req: Request, slot: AvailabilitySlot) -> None:
    from booker_api.compatibility import resource_available
    from booker_api.presentation import presentation_data

    _require_open_event(event)
    if not event.ends_at:
        raise HTTPException(409, "Уточните время окончания события перед предложением или резервом")
    start, end = aware(event.event_date), aware(event.ends_at)
    if start <= now() or end <= start:
        raise HTTPException(409, "Для предложения и резерва нужно будущее время события")
    if not _slot_matches_request(db, slot, req):
        raise HTTPException(409, "Слот не относится к ресурсу заявки")
    before = after = 0
    if req.resource_type == "artist":
        artist = db.get(Artist, req.resource_id)
        technical = (presentation_data(db, artist)[1].get("technical") or {}) if artist else {}
        before, after = technical.get("setup_minutes") or 0, technical.get("teardown_minutes") or 0
    blockers = db.query(AvailabilitySlot).filter(AvailabilitySlot.resource_type == slot.resource_type,
        AvailabilitySlot.resource_id == slot.resource_id, AvailabilitySlot.id != slot.id,
        AvailabilitySlot.status.in_(["busy", "held", "confirmed"])).all()
    if slot.status != "open" or not resource_available(db, slot.resource_type, slot.resource_id,
            start, end, before=before, after=after, slots=[slot, *blockers]):
        raise HTTPException(409, "Свободный интервал не покрывает время события с подготовкой и завершением")


def _honorarium_for_request(db: Session, req: Request) -> int | None:
    if req.resource_type == "artist":
        tariff = db.query(ArtistTariff).filter(ArtistTariff.artist_id == req.resource_id).order_by(ArtistTariff.honorarium_rub, ArtistTariff.id).first()
        return tariff.honorarium_rub if tariff else None
    if req.resource_type in {"venue", "hall"}:
        venue_id = req.resource_id
        if req.resource_type == "hall":
            hall = db.get(VenueHall, req.resource_id)
            venue_id = hall.venue_id if hall else req.resource_id
        tariff = db.query(VenueTariff).filter(VenueTariff.venue_id == venue_id).order_by(VenueTariff.honorarium_rub, VenueTariff.id).first()
        return tariff.honorarium_rub if tariff else None
    return None

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


def expire_holds(db: Session, *, limit: int | None = None) -> int:
    expired = 0
    moment = now()
    query = db.query(BookingHold).filter(BookingHold.status == "active", BookingHold.expires_at <= moment).order_by(BookingHold.expires_at, BookingHold.id)
    holds = query.limit(limit).all() if limit is not None else query.all()
    for hold in holds:
        if aware(hold.expires_at) > moment:
            continue
        changed = db.execute(update(BookingHold).where(BookingHold.id == hold.id, BookingHold.status == 'active', BookingHold.expires_at <= moment).values(status='expired'))
        if not changed.rowcount:
            continue
        slot = db.get(AvailabilitySlot, hold.slot_id)
        booking = db.get(Booking, hold.booking_id)
        if slot and slot.status == "held":
            other_live = db.query(BookingHold).filter(BookingHold.slot_id == slot.id, BookingHold.id != hold.id, BookingHold.status == 'active', BookingHold.expires_at > moment).first()
            if not other_live:
                db.execute(update(AvailabilitySlot).where(AvailabilitySlot.id == slot.id, AvailabilitySlot.status == 'held').values(status='open'))
        newer_hold = db.query(BookingHold).filter(BookingHold.booking_id == hold.booking_id, BookingHold.status == 'active', BookingHold.expires_at > moment).first()
        cancelled = db.execute(update(Booking).where(Booking.id == booking.id, Booking.status == 'DateHeld').values(status='Cancelled').execution_options(synchronize_session='fetch')).rowcount if booking and not newer_hold else 0
        if cancelled:
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
        if booking and not newer_hold and booking.status not in {'Confirmed', 'InProgress', 'Completed'}:
            from booker_api.notifications.lifecycle import booking_notice
            booking_notice(db, booking, template='hold.expired', subject='Срок удержания даты истёк',
                body='Прежний резерв больше не удерживает дату. Перед продолжением проверьте календарь и актуальные условия сделки.', key=hold.id)
        audit(
            db,
            actor_user_id=None,
            action="hold.expired",
            entity_type="booking",
            entity_id=hold.booking_id,
        )
    return expired


@router.post("/events")
def create_event(body: EventIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    key = body.idempotency_key
    body = body.model_dump(mode="json", exclude={"idempotency_key"})
    organization_id = body.get("organization_id")
    title = body.get("title")
    event_date = body.get("event_date")
    require_org_writer(db, user, organization_id)
    upload_limiter.check(f"event-create:{user.id}")
    db.execute(update(Organization).where(Organization.id == organization_id).values(name=Organization.name))
    scope = f"event.create:{organization_id}"
    cached = replay_command(db, scope, key, body)
    if cached:
        return cached
    event = Event(
        organization_id=organization_id,
        title=title,
        city=body.get("city", "Москва"),
        event_date=datetime.fromisoformat(event_date)
        if isinstance(event_date, str)
        else event_date,
        ends_at=datetime.fromisoformat(body["ends_at"]) if body.get("ends_at") else None,
        event_type=body.get("event_type", ""),
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
    result = {"id": event.id, "status": event.status, "requirements": requirements}
    remember_command(db, scope, key, body, result)
    audit(db, actor_user_id=user.id, action="event.created", entity_type="event", entity_id=event.id,
          payload={"organization_id": event.organization_id, "requirements_count": len(requirements), "has_end": event.ends_at is not None})
    db.commit()
    return result


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
                "ends_at": e.ends_at.isoformat() if e.ends_at else None,
                "event_type": e.event_type,
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
            "booking_status": booking.status if booking else None,
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
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "event_type": event.event_type,
        "budget_rub": event.budget_rub,
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
    member = require_org_member(db, user, event.organization_id)
    analytics_limiter.check(f"replacement:{user.id}")
    requirement = db.get(EventTeamRequirement, requirement_id)
    if not requirement or requirement.event_id != event.id:
        raise HTTPException(404, "Позиция состава не найдена")
    plan = build_replacement_plan(db, event, requirement)
    plan["can_manage"] = member.role in {"owner", "admin", "manager"} or user.is_platform_admin
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


@router.post("/events/{event_id}/requirements/{requirement_id}/replacement-requests")
def create_replacement_request(
    event_id: str,
    requirement_id: str,
    body: RequestCreateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    messaging_limiter.check(f"replacement-create:{user.id}")
    if not body.idempotency_key or str(body.requirement_id) != requirement_id or body.promotion_touch_id:
        raise HTTPException(422, "Укажите позицию события и ключ повторной отправки")
    requirement = db.get(EventTeamRequirement, requirement_id)
    if not requirement or requirement.event_id != event.id:
        raise HTTPException(404, "Позиция состава не найдена")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    payload = body.model_dump(mode="json", exclude={"idempotency_key"})
    cached = replay_command(db, f"request.create:{event.id}", body.idempotency_key, payload)
    if cached:
        return cached
    db.refresh(event)
    _require_open_event(event)
    plan = build_replacement_plan(db, event, requirement)
    def matches(item):
        kind = "hall" if item.get("hall_id") else item["resource_type"]
        target = item.get("hall_id") or item["resource_id"]
        return kind == body.resource_type and target == str(body.resource_id)
    if not any(matches(item) for item in plan["candidates"]):
        raise HTTPException(409, "Вариант больше не доступен для замены. Обновите подбор")
    audit(db, actor_user_id=user.id, action="replacement.requested", entity_type="requirement",
        entity_id=requirement.id, payload={"resource_type": body.resource_type, "resource_id": str(body.resource_id)})
    # The existing request command commits the request, notification and receipt together.
    return create_request(event_id, body, user, db)


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
    from booker_api.notifications.lifecycle import booking_notice
    booking_notice(db, booking, template='booking.cancelled', subject='Участник сделки отменён',
        body='Сделка отменена. Проверьте состав события и связанные документы в кабинете.', key=booking.id, actor_id=user.id)
    if req.requirement_id and event.status not in {'Cancelled', 'Completed'}:
        booking_notice(db, booking, template='replacement.required', subject='Проверьте замену участника',
            body='После отмены сделки проверьте состав события. В кабинете можно посмотреть доступные варианты замены; наличие подходящей замены не гарантируется.',
            key=booking.id, customer_only=True, event_link=True, actor_id=user.id)
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
        db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
        db.refresh(event)
        _require_open_event(event)
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
            ends_at=slot.ends_at,
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
    if event.status in {"Draft", "RequestSent"}:
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
    attribute_request(db, req, body.get("promotion_touch_id"), user.id)
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
    body: RequestCreateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    key = body.idempotency_key
    body = body.model_dump(mode="json", exclude={"idempotency_key"})
    messaging_limiter.check(f"request-create:{user.id}")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    scope = f"request.create:{event.id}"
    cached = replay_command(db, scope, key, body)
    if cached:
        return cached
    db.refresh(event)
    _require_open_event(event)
    resource_type = body["resource_type"]
    resource_id = body["resource_id"]
    if resource_type == "artist":
        artist = db.get(Artist, resource_id)
        if not artist:
            raise HTTPException(404, "Артист не найден")
        supplier_org_id = artist.organization_id
    elif resource_type == "hall":
        hall = db.get(VenueHall, resource_id)
        if not hall:
            raise HTTPException(404, "Зал не найден")
        venue = db.get(Venue, hall.venue_id)
        if not venue:
            raise HTTPException(404, "Площадка не найдена")
        supplier_org_id = venue.organization_id
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
    if event.status in {"Draft", "RequestSent"}:
        event.status = "RequestSent"
    audit(
        db,
        actor_user_id=user.id,
        action="request.created",
        entity_type="request",
        entity_id=req.id,
    )
    attribute_request(db, req, body.get("promotion_touch_id"), user.id)
    on_request_created(
        db,
        actor_user_id=user.id,
        request_id=req.id,
        supplier_org_id=supplier_org_id,
        event_title=event.title,
    )
    result = {"id": req.id, "status": req.status}
    remember_command(db, scope, key, body, result)
    db.commit()
    return result


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
    if type(raw_honorarium) is not int or raw_honorarium > 1_000_000_000:
        raise HTTPException(400, "Гонорар должен быть целым числом рублей до 1 млрд")
    try:
        honorarium = int(raw_honorarium)
    except (TypeError, ValueError):
        raise HTTPException(400, "honorarium_rub должен быть числом") from None
    if honorarium <= 0:
        raise HTTPException(400, "honorarium_rub должен быть больше нуля")
    event = db.get(Event, req.event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    db.refresh(event)
    _require_open_event(event)
    breakdown = offer_fees(db, honorarium, req.supplier_org_id, event.organization_id)
    slot_id = body.get("slot_id")
    if not slot_id:
        raise HTTPException(400, "slot_id обязателен")
    slot = db.get(AvailabilitySlot, slot_id)
    if not slot:
        raise HTTPException(404, "Слот не найден")
    if not _slot_matches_request(db, slot, req):
        raise HTTPException(400, "Слот не относится к ресурсу заявки")
    _validate_event_slot(db, event, req, slot)
    offer = Offer(request_id=req.id)
    db.add(offer)
    db.flush()
    version = OfferVersion(
        offer_id=offer.id,
        honorarium_rub=breakdown["honorarium_rub"],
        commission_rate=breakdown["commission_rate"],
        commission_rub=breakdown["commission_rub"],
        total_rub=breakdown["total_rub"],
        **{field: breakdown[field] for field in SNAPSHOT_FIELDS},
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
    if event and event.status in {"Draft", "RequestSent", "Negotiation"}:
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
    if type(raw_honorarium) is not int or raw_honorarium > 1_000_000_000:
        raise HTTPException(400, "Гонорар должен быть целым числом рублей до 1 млрд")
    try:
        honorarium = int(raw_honorarium)
    except (TypeError, ValueError):
        raise HTTPException(400, "honorarium_rub должен быть числом") from None
    if honorarium <= 0:
        raise HTTPException(400, "honorarium_rub должен быть больше нуля")
    booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()
    if booking and booking.status != "Negotiation":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Условия зафиксированы удержанием даты или закрытием сделки",
        )
    breakdown = offer_fees(db, honorarium, req.supplier_org_id, event.organization_id)
    version = OfferVersion(
        offer_id=offer.id,
        honorarium_rub=breakdown["honorarium_rub"],
        commission_rate=breakdown["commission_rate"],
        commission_rub=breakdown["commission_rub"],
        total_rub=breakdown["total_rub"],
        **{field: breakdown[field] for field in SNAPSHOT_FIELDS},
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


def _assert_hold_ready(db: Session, booking: Booking) -> OfferVersion:
    event = db.get(Event, booking.event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    db.refresh(event)
    _require_open_event(event)
    db.refresh(booking)
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id) if offer else None
    if not version or not (version.customer_ack and version.supplier_ack):
        raise HTTPException(409, "Оффер не подтверждён обеими сторонами")
    if booking.status != "Negotiation":
        raise HTTPException(status.HTTP_409_CONFLICT, "Бронь уже удержана или закрыта")
    return version


def _lock_and_validate_slot(db: Session, booking: Booking) -> AvailabilitySlot:
    slot = db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == booking.slot_id).with_for_update()
    ).scalar_one()
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    event = db.get(Event, booking.event_id)
    if not event or not req or req.event_id != event.id:
        raise HTTPException(409, "Данные заявки и события не совпадают")
    _validate_event_slot(db, event, req, slot)
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
    return slot


def _apply_hold(db: Session, *, booking: Booking, slot: AvailabilitySlot, actor_user_id: str) -> BookingHold:
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
        actor_user_id=actor_user_id,
        action="hold.created",
        entity_type="booking",
        entity_id=booking.id,
    )
    return hold


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
        require_org_writer(db, user, sup_org)
    else:
        raise HTTPException(403, "Нет доступа")
    _assert_hold_ready(db, booking)
    slot = _lock_and_validate_slot(db, booking)
    hold = _apply_hold(db, booking=booking, slot=slot, actor_user_id=user.id)
    db.commit()
    db.refresh(hold)
    return {"hold_id": hold.id, "expires_at": hold.expires_at.isoformat(), "status": booking.status}


@router.post("/events/{event_id}/holds/atomic")
def hold_bookings_atomic(
    event_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """E10: hold an obligatory set of bookings (e.g. multi-hall) all-or-nothing."""
    expire_holds(db)
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    booking_ids = body.get("booking_ids") or []
    if not isinstance(booking_ids, list) or len(booking_ids) < 2:
        raise HTTPException(400, "Нужен обязательный набор из ≥2 бронирований")
    if len(set(booking_ids)) != len(booking_ids):
        raise HTTPException(400, "Дубликаты booking_ids запрещены")

    bookings: list[Booking] = []
    for bid in booking_ids:
        booking = db.get(Booking, bid)
        if not booking or booking.event_id != event_id:
            raise HTTPException(404, "Бронь не найдена в этом событии")
        bookings.append(booking)

    for booking in bookings:
        _assert_hold_ready(db, booking)

    # Lock slots in deterministic order to avoid deadlocks; validate all before any claim.
    ordered = sorted(bookings, key=lambda b: b.slot_id)
    slots: list[tuple[Booking, AvailabilitySlot]] = []
    for booking in ordered:
        slots.append((booking, _lock_and_validate_slot(db, booking)))

    holds_out = []
    for booking, slot in slots:
        hold = _apply_hold(db, booking=booking, slot=slot, actor_user_id=user.id)
        holds_out.append(
            {
                "booking_id": booking.id,
                "hold_id": hold.id,
                "expires_at": hold.expires_at.isoformat(),
                "status": booking.status,
            }
        )
    audit(
        db,
        actor_user_id=user.id,
        action="hold.atomic_package",
        entity_type="event",
        entity_id=event_id,
        payload={"booking_ids": booking_ids, "count": len(booking_ids)},
    )
    db.commit()
    return {"ok": True, "holds": holds_out}


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
    from booker_api.security import membership

    customer_member = membership(db, user.id, event.organization_id)
    payment_writer = user.is_platform_admin or bool(
        customer_member and customer_member.role in {"owner", "admin", "manager"}
    )
    hold_member = customer_member or membership(db, user.id, req.supplier_org_id)
    hold_writer = user.is_platform_admin or bool(hold_member and hold_member.role in {"owner", "admin", "manager"})
    can_hold = bool(hold_writer and event.status not in {"Completed", "Cancelled"}
        and booking.status == "Negotiation" and version and version.customer_ack and version.supplier_ack)
    capabilities = payment_capabilities()
    capabilities["can_create"] = bool(
        payment_writer and capabilities["available"] and booking.status == "AwaitingPayment"
        and (not payment or payment.status in {"pending", "failed"})
    )
    capabilities["can_test_complete"] = bool(
        payment_writer and capabilities["test_mode"] and payment and payment.provider == "stub"
        and payment.status in {"pending", "failed"}
    )
    loss = db.query(AuditLog).filter_by(action="request.loss_reason", entity_id=req.id).order_by(AuditLog.created_at.desc()).first()
    return {
        "booking_id": booking.id,
        "offer_id": offer.id,
        "request_id": req.id,
        "loss_reason": json.loads(loss.payload).get("reason") if loss else None,
        "event_id": event.id,
        "requirement_id": getattr(req, "requirement_id", None),
        "status": booking.status,
        "role": role,
        "workspace_kind": workspace_kind,
        "can_hold": can_hold,
        "event_title": event.title,
        "tabs": ["chat", "terms", "documents", "payments", "dispute"],
        "dispute_categories": [
            {"id": "no_show", "label": "Неявка"},
            {"id": "delay", "label": "Опоздание"},
            {"id": "quality", "label": "Качество услуги"},
            {"id": "payment", "label": "Платёж"},
            {"id": "cancel", "label": "Отмена"},
        ],
        "next_step": ("Проверить доступность и удержать дату" if booking.status == "Negotiation" and version and version.customer_ack and version.supplier_ack else _next_step(booking.status)),
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
            "otp_pending": not (contract.customer_signed and contract.supplier_signed),
        },
        "documents": _deal_documents(version, contract, attachments),
        "payment_capabilities": capabilities,
        "payment": None
        if not payment
        else {
            "id": payment.id,
            "status": payment.status,
            "amount_rub": payment.amount_rub,
            "provider": payment.provider,
            "requires_operator": payment.status == "succeeded" and booking.status in {"AwaitingPayment", "Cancelled"},
        },
        "quote": {
            **snapshot_payload(version),
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
                if version.commercial_policy_version is None and version.commission_rub == 0
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


@router.get("/messages/inbox")
def messages_inbox(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Message hub: deal-room threads the user can access (§19 / W4-MSG-HUB)."""
    from booker_api.models import TeamMember

    org_ids = [
        m.organization_id
        for m in db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    ]
    if user.is_platform_admin:
        convs = db.query(Conversation).order_by(Conversation.id.desc()).limit(100).all()
    else:
        if not org_ids:
            return {"items": []}
        convs = db.query(Conversation).all()

    items: list[dict] = []
    for conv in convs:
        booking = db.get(Booking, conv.booking_id)
        if not booking:
            continue
        try:
            cust_org, sup_org = _booking_participant_orgs(db, booking)
        except (AttributeError, TypeError):
            # Broken booking graph (missing offer/request/event) — skip inbox row.
            cust_org, sup_org = "", ""
        if not cust_org or not sup_org:
            continue
        if not user.is_platform_admin and cust_org not in org_ids and sup_org not in org_ids:
            continue
        last = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        event = db.get(Event, booking.event_id)
        cust_name = db.get(Organization, cust_org)
        sup_name = db.get(Organization, sup_org)
        items.append(
            {
                "conversation_id": conv.id,
                "booking_id": booking.id,
                "booking_status": booking.status,
                "event_title": event.title if event else "",
                "customer_org": cust_name.name if cust_name else cust_org,
                "supplier_org": sup_name.name if sup_name else sup_org,
                "deal_path": f"/deals/{booking.id}",
                "last_message": (
                    {
                        "id": last.id,
                        "kind": last.kind,
                        "body": last.body[:240],
                        "created_at": last.created_at.isoformat() if last.created_at else None,
                    }
                    if last
                    else None
                ),
            }
        )

    items.sort(
        key=lambda x: (x["last_message"] or {}).get("created_at") or "",
        reverse=True,
    )
    return {"items": items[:50]}


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
