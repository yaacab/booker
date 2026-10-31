import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request as HttpRequest
from starlette.responses import Response

from booker_api.calendar import overlapping_slots
from booker_api.composition import ensure_requirements, replace_requirements, requirement_payload
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.disputes import ACTIVE_DISPUTE_STATUSES, create_dispute, dispute_payload
from booker_api.event_day import (
    build_day_status,
    check_in_booking,
    check_in_event,
    check_out_booking,
    check_out_event,
)
from booker_api.event_readiness import build_event_readiness
from booker_api.external_evidence import effective_review_state
from booker_api.file_scan import safe_media_type, scan_upload
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    BookingHold,
    Contract,
    ContractSignature,
    Conversation,
    ConversationReadState,
    DealAttachment,
    Dispute,
    DisputeEvidence,
    Event,
    EventTeamRequirement,
    ExternalPaymentEvent,
    ExternalPaymentReport,
    Message,
    Offer,
    OfferAcknowledgement,
    OfferVersion,
    Organization,
    Payment,
    PaymentObligation,
    PaymentPlan,
    Request,
    TeamMember,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.notifications import on_offer_created, on_request_created
from booker_api.payment_obligations import ensure_payment_plan
from booker_api.payment_scheduler import (
    build_payment_terms_snapshot,
    obligation_payload,
    serialize_payment_terms,
    version_payment_terms,
)
from booker_api.pricing import first_deal_waive, price_breakdown
from booker_api.publication_eligibility import (
    artist_publication_eligibility,
    venue_publication_eligibility,
)
from booker_api.rate_limit import (
    client_key,
    messaging_limiter,
    request_creation_limiter,
    upload_limiter,
)
from booker_api.replacement import build_replacement_plan
from booker_api.schemas import DisputeEvidenceIn, DisputeIn, MessageIn
from booker_api.security import (
    AuthContext,
    audit,
    auth_context,
    authenticate_token,
    aware,
    current_user,
    ensure_admin_2fa_session,
    hold_deadline,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["deals"])


def attachment_is_downloadable(row: DealAttachment) -> bool:
    if row.scan_status != "clean":
        return False
    if settings.av_provider == "clamd":
        return row.av_verdict_provider == "clamd" and hmac.compare_digest(
            row.av_verdict_sha256 or "", row.sha256
        )
    return True


def attachment_effective_scan_status(row: DealAttachment) -> str:
    if row.scan_status == "clean" and not attachment_is_downloadable(row):
        return "quarantined"
    return row.scan_status


def read_verified_attachment(row: DealAttachment) -> bytes:
    """Read an attachment only when the stored object matches its immutable metadata."""
    root = Path(settings.upload_dir).resolve()
    path = (root / row.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Файл не найден")
    if row.size_bytes > settings.max_upload_bytes or path.stat().st_size != row.size_bytes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Целостность файла не подтверждена")
    with path.open("rb") as stored:
        raw = stored.read(settings.max_upload_bytes + 1)
    if len(raw) != row.size_bytes or not hmac.compare_digest(
        hashlib.sha256(raw).hexdigest(), row.sha256
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Целостность файла не подтверждена")
    return raw


def _request_participant_orgs(db: Session, req: Request) -> tuple[str, str]:
    conversation = (
        db.query(Conversation).filter(Conversation.request_id == req.id).one_or_none()
    )
    if conversation and conversation.customer_org_id and conversation.supplier_org_id:
        return conversation.customer_org_id, conversation.supplier_org_id
    event = db.get(Event, req.event_id)
    if not event:
        raise HTTPException(404, "Событие заявки не найдено")
    return event.organization_id, req.supplier_org_id


def _conversation_request(db: Session, conv: Conversation) -> Request | None:
    if conv.request_id:
        return db.get(Request, conv.request_id)
    if not conv.booking_id:
        return None
    booking = db.get(Booking, conv.booking_id)
    offer = db.get(Offer, booking.offer_id) if booking else None
    return db.get(Request, offer.request_id) if offer else None


def _require_conversation_access(
    db: Session, user: User, conv: Conversation
) -> tuple[Request, str, str]:
    req = _conversation_request(db, conv)
    if not req:
        raise HTTPException(404, "Диалог не найден")
    customer_org_id = conv.customer_org_id
    supplier_org_id = conv.supplier_org_id
    if not customer_org_id or not supplier_org_id:
        raise HTTPException(404, "Диалог не найден")
    memberships = (
        db.query(TeamMember)
        .filter(
            TeamMember.user_id == user.id,
            TeamMember.organization_id.in_([customer_org_id, supplier_org_id]),
        )
        .all()
    )
    if not memberships:
        raise HTTPException(404, "Диалог не найден")
    return req, customer_org_id, supplier_org_id


def _require_conversation_writer(db: Session, user: User, conv: Conversation) -> Request:
    req, customer_org_id, supplier_org_id = _require_conversation_access(db, user, conv)
    memberships = (
        db.query(TeamMember)
        .filter(
            TeamMember.user_id == user.id,
            TeamMember.organization_id.in_([customer_org_id, supplier_org_id]),
        )
        .all()
    )
    if not any(member.role in {"owner", "admin", "manager"} for member in memberships):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только просмотр: нужна роль менеджера")
    return req


def _message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "author_user_id": message.author_user_id,
        "author_org_id": message.author_org_id,
        "author_side": message.author_side,
        "author_name": message.author_name_snapshot,
        "actor_role": message.actor_role_snapshot,
        "attribution_status": message.attribution_status,
        "kind": message.kind,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


def _message_replay_matches(
    message: Message,
    *,
    user_id: str,
    organization_id: str,
    side: str,
    body: str,
) -> bool:
    return (
        message.author_user_id == user_id
        and message.author_org_id == organization_id
        and message.author_side == side
        and message.kind == "chat"
        and message.body == body
    )


def _race_safe_message_flush(
    db: Session,
    message: Message,
    *,
    user_id: str,
    organization_id: str,
    side: str,
    body: str,
) -> Message | None:
    """Return the winning equivalent row when concurrent retries share a key."""
    try:
        db.flush()
        return None
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Message)
            .filter_by(
                conversation_id=message.conversation_id,
                idempotency_key=message.idempotency_key,
            )
            .one_or_none()
        )
        if existing and _message_replay_matches(
            existing,
            user_id=user_id,
            organization_id=organization_id,
            side=side,
            body=body,
        ):
            return existing
        raise HTTPException(
            409, "Ключ повторного запроса использован с другими данными"
        ) from None


def _create_request_conversation(db: Session, req: Request) -> Conversation:
    customer_org_id, supplier_org_id = _request_participant_orgs(db, req)
    customer_org = db.get(Organization, customer_org_id)
    supplier_org = db.get(Organization, supplier_org_id)
    if not customer_org or not supplier_org:
        raise HTTPException(409, "Организации участников не найдены")
    conv = Conversation(
        request_id=req.id,
        customer_org_id=customer_org_id,
        supplier_org_id=supplier_org_id,
        customer_name_snapshot=customer_org.name,
        supplier_name_snapshot=supplier_org.name,
    )
    db.add(conv)
    db.flush()
    db.add(
        Message(
            conversation_id=conv.id,
            kind="system",
            body="Заявка отправлена. Общение доступно обеим сторонам.",
        )
    )
    return conv


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


def _slot_matches_request(db: Session, slot: AvailabilitySlot, req: Request) -> bool:
    """Artist/hall exact match; venue requests may use a hall slot of that venue."""
    if slot.resource_type == req.resource_type and slot.resource_id == req.resource_id:
        return True
    if req.resource_type == "venue" and slot.resource_type == "hall":
        hall = db.get(VenueHall, slot.resource_id)
        return bool(hall and hall.venue_id == req.resource_id)
    return False


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


def _payment_terms(body: dict, total_rub: int, event_date: datetime) -> dict:
    try:
        advance_rub = int(body.get("advance_rub", total_rub))
        security_deposit_rub = int(body.get("security_deposit_rub", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "Суммы графика платежей должны быть целыми числами") from None
    if advance_rub <= 0 or advance_rub > total_rub:
        raise HTTPException(400, "Аванс должен быть больше нуля и не превышать стоимость сделки")
    if security_deposit_rub < 0:
        raise HTTPException(400, "Обеспечительный платёж не может быть отрицательным")
    amounts = {
        "advance_rub": advance_rub,
        "balance_rub": total_rub - advance_rub,
        "security_deposit_rub": security_deposit_rub,
    }
    try:
        snapshot = build_payment_terms_snapshot(
            body,
            amounts={
                "advance": amounts["advance_rub"],
                "balance": amounts["balance_rub"],
                "security_deposit": amounts["security_deposit_rub"],
            },
            event_date=event_date,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**amounts, "payment_terms_json": serialize_payment_terms(snapshot)}


def _payment_terms_response(version: OfferVersion) -> dict:
    return {
        "advance_rub": version.advance_rub,
        "balance_rub": version.balance_rub,
        "security_deposit_rub": version.security_deposit_rub,
        "payment_terms": version_payment_terms(version),
    }

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
        "guest_count": event.guest_count,
        "notes": event.notes,
        "organization_id": event.organization_id,
        "requirements": requirements,
        "requests": requests,
        "readiness": build_event_readiness(db, event),
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
                "quote_id": offer.active_version_id if offer else None,
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
        "readiness": build_event_readiness(db, event),
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
    event = db.query(Event).filter(Event.id == event_id).with_for_update().one_or_none()
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
def booking_check_in(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    booking_ref = db.get(Booking, booking_id)
    if not booking_ref:
        raise HTTPException(404, "Бронь не найдена")
    event = (
        db.query(Event)
        .filter(Event.id == booking_ref.event_id)
        .with_for_update()
        .one_or_none()
    )
    if not event:
        raise HTTPException(404, "Сделка не найдена")
    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id)
        .with_for_update()
        .one_or_none()
    )
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    side, acting_org_id, _member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=None,
        writer_required=True,
    )
    readiness = build_event_readiness(db, event, lock=True)
    if readiness["state"] != "ready":
        raise HTTPException(409, "Обязательный состав события не готов")
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
        payload={"side": side, "acting_org_id": acting_org_id},
    )
    db.commit()
    return {"booking_id": booking.id, "status": status, "event_status": event.status}


@router.post("/bookings/{booking_id}/check-out")
def booking_check_out(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = db.get(Event, booking.event_id)
    if not event:
        raise HTTPException(404, "Сделка не найдена")
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    side, acting_org_id, _member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=None,
        writer_required=True,
    )
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
        payload={"side": side, "acting_org_id": acting_org_id},
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
    request: HttpRequest,
    body: dict | None = None,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
):
    user = ctx.user
    if user.is_platform_admin:
        ensure_admin_2fa_session(request, db, user, ctx.session, force=True)
    expire_holds(db)
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id) if offer else None
    event = db.get(Event, booking.event_id)
    if not req or not event:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not user.is_platform_admin and not (
        db.query(TeamMember.id)
        .filter(
            TeamMember.user_id == user.id,
            TeamMember.organization_id.in_({cust_org, sup_org}),
            TeamMember.role.in_({"owner", "admin", "manager"}),
        )
        .first()
    ):
        raise HTTPException(403, "Нет права отменять бронь")
    if booking.status in {"Cancelled", "Completed"}:
        raise HTTPException(409, "Бронь уже закрыта")
    # Serialize against payment creation on the same offer, then inspect payment
    # rows under their locks. A late capture or external report must not land on
    # an automatically released slot.
    locked_offer = (
        db.query(Offer)
        .filter(Offer.id == booking.offer_id)
        .with_for_update()
        .one_or_none()
    )
    if not locked_offer:
        raise HTTPException(409, "Предложение брони недоступно")
    db.refresh(booking)
    if booking.status in {"Cancelled", "Completed"}:
        raise HTTPException(409, "Бронь уже закрыта")
    financial_rows = (
        db.query(Payment)
        .filter(Payment.booking_id == booking.id)
        .order_by(Payment.id)
        .with_for_update()
        .all()
    )
    if any(row.status != "failed" for row in financial_rows):
        raise HTTPException(
            409,
            "По брони есть платёж или внешний перевод. Отмена требует проверки расчётов через поддержку или спор.",
        )
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
    event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .with_for_update()
        .one_or_none()
    )
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    bound_contract = (
        db.query(Contract.id)
        .join(Booking, Booking.id == Contract.booking_id)
        .filter(Booking.event_id == event.id)
        .first()
    )
    if bound_contract:
        raise HTTPException(
            409,
            "Состав события зафиксирован в черновике условий; требуется отдельное изменение сделки",
        )
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
    rows = (
        db.query(Request)
        .outerjoin(Conversation, Conversation.request_id == Request.id)
        .filter(
            or_(
                Conversation.supplier_org_id.in_(ids),
                and_(Conversation.id.is_(None), Request.supplier_org_id.in_(ids)),
            )
        )
        .all()
        if ids
        else []
    )
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
    rows = (
        db.query(Booking)
        .join(Conversation, Conversation.booking_id == Booking.id)
        .filter(
            or_(
                Conversation.customer_org_id.in_(ids),
                Conversation.supplier_org_id.in_(ids),
            )
        )
        .all()
        if ids
        else []
    )
    items = []
    for booking in rows:
        offer = db.get(Offer, booking.offer_id)
        req = db.get(Request, offer.request_id) if offer else None
        event = db.get(Event, booking.event_id)
        if not req or not event:
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
def quick_request(
    body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    request_creation_limiter.check(f"quick:u:{user.id}")
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
    if not artist_publication_eligibility(db, artist, required_through=slot.ends_at).eligible:
        raise HTTPException(404, "Артист не найден")
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
    _create_request_conversation(db, req)
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
    request_creation_limiter.check(f"request:u:{user.id}:org:{event.organization_id}")
    resource_type = body["resource_type"]
    resource_id = body["resource_id"]
    if resource_type == "artist":
        artist = db.get(Artist, resource_id)
        if not artist or not artist_publication_eligibility(
            db, artist, required_through=event.event_date
        ).eligible:
            raise HTTPException(404, "Артист не найден")
        supplier_org_id = artist.organization_id
    elif resource_type == "hall":
        hall = db.get(VenueHall, resource_id)
        if not hall:
            raise HTTPException(404, "Зал не найден")
        venue = db.get(Venue, hall.venue_id)
        if not venue or not venue_publication_eligibility(
            db, venue, required_through=event.event_date
        ).eligible:
            raise HTTPException(404, "Площадка не найдена")
        supplier_org_id = venue.organization_id
    else:
        venue = db.get(Venue, resource_id)
        if not venue or not venue_publication_eligibility(
            db, venue, required_through=event.event_date
        ).eligible:
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
    _create_request_conversation(db, req)
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
    conv = db.query(Conversation).filter(Conversation.request_id == req.id).one_or_none()
    if not conv:
        raise HTTPException(status.HTTP_409_CONFLICT, "Диалог заявки не найден")
    member = require_org_writer(db, user, conv.supplier_org_id)
    if not member.can_confirm_offer and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет права подтверждать оффер")
    if db.query(Offer.id).filter(Offer.request_id == req.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Для заявки уже создано предложение")
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
    waive = bool(event and first_deal_waive(db, conv.customer_org_id))
    breakdown = price_breakdown(honorarium, waive_commission=waive)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    payment_terms = _payment_terms(body, breakdown["total_rub"], event.event_date)
    slot_id = body.get("slot_id")
    if not slot_id:
        raise HTTPException(400, "slot_id обязателен")
    slot = db.get(AvailabilitySlot, slot_id)
    if not slot:
        raise HTTPException(404, "Слот не найден")
    if not _slot_matches_request(db, slot, req):
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
        **payment_terms,
        terms=body.get("terms", ""),
    )
    db.add(version)
    db.flush()
    ensure_payment_plan(db, version)
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
    conv.booking_id = booking.id
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
            customer_org_id=conv.customer_org_id,
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
            **_payment_terms_response(version),
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
    offer = db.query(Offer).filter_by(id=offer_id).with_for_update().one_or_none()
    if not offer:
        raise HTTPException(404, "Оффер не найден")
    req = db.get(Request, offer.request_id)
    event = db.get(Event, req.event_id)
    customer_org_id, supplier_org_id = _request_participant_orgs(db, req)
    if membership_ok(db, user, supplier_org_id):
        require_org_writer(db, user, supplier_org_id)
    elif membership_ok(db, user, customer_org_id):
        require_org_writer(db, user, customer_org_id)
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
    if booking and db.query(Contract.id).filter(Contract.booking_id == booking.id).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Договор уже выпущен: новая цена требует нового договора",
        )
    waive = bool(
        event
        and first_deal_waive(db, event.organization_id, exclude_booking_id=booking.id if booking else None)
    )
    breakdown = price_breakdown(honorarium, waive_commission=waive)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    payment_terms = _payment_terms(body, breakdown["total_rub"], event.event_date)
    version = OfferVersion(
        offer_id=offer.id,
        honorarium_rub=breakdown["honorarium_rub"],
        commission_rate=breakdown["commission_rate"],
        commission_rub=breakdown["commission_rub"],
        total_rub=breakdown["total_rub"],
        **payment_terms,
        terms=body.get("terms", ""),
        customer_ack=False,
        supplier_ack=False,
    )
    db.add(version)
    db.flush()
    ensure_payment_plan(db, version)
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
    return {
        "id": version.id,
        "quote_id": version.id,
        **breakdown,
        **_payment_terms_response(version),
        "active": False,
    }


def membership_ok(db, user, org_id) -> bool:
    from booker_api.security import membership

    return bool(membership(db, user.id, org_id) or user.is_platform_admin)


def _resolve_acting_party(
    db: Session,
    user: User,
    customer_org_id: str,
    supplier_org_id: str,
    *,
    x_booker_org: str | None,
    claimed_side: str | None,
    writer_required: bool,
) -> tuple[str, str, TeamMember]:
    """Resolve a deal side from authenticated membership, never from client side alone."""
    if claimed_side is not None and claimed_side not in {"customer", "supplier"}:
        raise HTTPException(400, "side: customer|supplier")
    party_by_org = {
        customer_org_id: "customer",
        supplier_org_id: "supplier",
    }
    memberships = (
        db.query(TeamMember)
        .filter(
            TeamMember.user_id == user.id,
            TeamMember.organization_id.in_(party_by_org),
        )
        .all()
    )
    if writer_required:
        memberships = [
            member for member in memberships if member.role in {"owner", "admin", "manager"}
        ]
    by_org = {member.organization_id: member for member in memberships}
    acting_org_id = (x_booker_org or "").strip() or None
    if acting_org_id:
        if acting_org_id not in party_by_org:
            raise HTTPException(409, "Активная организация не является стороной сделки")
        member = by_org.get(acting_org_id)
        if not member:
            raise HTTPException(403, "Нет права действовать от этой организации")
    else:
        eligible = [org_id for org_id in party_by_org if org_id in by_org]
        if not eligible:
            raise HTTPException(403, "Нет доступа")
        if len(eligible) > 1:
            raise HTTPException(409, "Выберите действующую организацию")
        acting_org_id = eligible[0]
        member = by_org[acting_org_id]
    side = party_by_org[acting_org_id]
    if claimed_side is not None and claimed_side != side:
        raise HTTPException(409, "side не совпадает с действующей организацией")
    return side, acting_org_id, member


@router.post("/offers/{offer_id}/ack")
def ack_offer(
    offer_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    offer = db.get(Offer, offer_id)
    if not offer or not offer.active_version_id:
        raise HTTPException(404, "Оффер не найден")
    version = db.get(OfferVersion, offer.active_version_id)
    req = db.get(Request, offer.request_id)
    customer_org_id, supplier_org_id = _request_participant_orgs(db, req)
    quote_id = body.get("quote_id")
    if not quote_id:
        raise HTTPException(400, "quote_id обязателен для подтверждения")
    if quote_id != version.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "quote_id устарел: подтверждается только активная версия предложения",
        )
    side, acting_org_id, member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=body.get("side"),
        writer_required=True,
    )
    if side == "supplier":
        if not member.can_confirm_offer:
            raise HTTPException(403, "Нет права подтверждать оффер")
        if (
            db.query(OfferAcknowledgement.id)
            .filter_by(offer_version_id=version.id, actor_user_id=user.id, side="customer")
            .first()
        ):
            raise HTTPException(409, "Один пользователь не может подтвердить обе стороны")
        if not version.supplier_ack:
            db.add(
                OfferAcknowledgement(
                    offer_version_id=version.id,
                    side="supplier",
                    organization_id=acting_org_id,
                    actor_user_id=user.id,
                    actor_role_snapshot=member.role,
                )
            )
            version.supplier_ack = True
    else:
        if (
            db.query(OfferAcknowledgement.id)
            .filter_by(offer_version_id=version.id, actor_user_id=user.id, side="supplier")
            .first()
        ):
            raise HTTPException(409, "Один пользователь не может подтвердить обе стороны")
        if not version.customer_ack:
            db.add(
                OfferAcknowledgement(
                    offer_version_id=version.id,
                    side="customer",
                    organization_id=acting_org_id,
                    actor_user_id=user.id,
                    actor_role_snapshot=member.role,
                )
            )
            version.customer_ack = True
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Подтверждение этой стороны уже зафиксировано") from exc
    both = version.customer_ack and version.supplier_ack
    if both:
        booking = db.query(Booking).filter(Booking.offer_id == offer.id).one_or_none()
        if booking:
            booking.accepted_offer_version_id = version.id
    audit(
        db,
        actor_user_id=user.id,
        action="offer.ack",
        entity_type="offer_version",
        entity_id=version.id,
        payload={"side": side, "acting_org_id": acting_org_id, "both": both},
    )
    db.commit()
    return {
        "quote_id": version.id,
        "honorarium_rub": version.honorarium_rub,
        "commission_rate": version.commission_rate,
        "commission_rub": version.commission_rub,
        "total_rub": version.total_rub,
        "advance_rub": version.advance_rub,
        "balance_rub": version.balance_rub,
        "security_deposit_rub": version.security_deposit_rub,
        "payment_terms": version_payment_terms(version),
        "customer_ack": version.customer_ack,
        "supplier_ack": version.supplier_ack,
        "active": both,
    }


def _assert_hold_ready(db: Session, booking: Booking) -> OfferVersion:
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id) if offer else None
    if not version or not (version.customer_ack and version.supplier_ack):
        raise HTTPException(409, "Оффер не подтверждён обеими сторонами")
    if booking.accepted_offer_version_id != version.id:
        raise HTTPException(409, "Принятая версия предложения не совпадает с текущей")
    if booking.status != "Negotiation":
        raise HTTPException(status.HTTP_409_CONFLICT, "Бронь уже удержана или закрыта")
    return version


def _lock_and_validate_slot(db: Session, booking: Booking) -> AvailabilitySlot:
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
    conversation = (
        db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    )
    if conversation and conversation.customer_org_id and conversation.supplier_org_id:
        return conversation.customer_org_id, conversation.supplier_org_id
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    return event.organization_id, req.supplier_org_id


@router.post("/bookings/{booking_id}/attachments")
async def upload_booking_attachment(
    booking_id: str,
    request: HttpRequest,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
):
    user = ctx.user
    if user.is_platform_admin:
        ensure_admin_2fa_session(request, db, user, ctx.session, force=True)
    upload_limiter.check(client_key(request, "upload"))
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
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    booking_dir = (root / booking_id).resolve()
    if root not in booking_dir.parents:
        raise HTTPException(500, "Некорректный путь хранилища")
    booking_dir.mkdir(parents=True, exist_ok=True)
    attachment_id = str(uuid4())
    storage_key = f"{booking_id}/{attachment_id}"
    path = root / storage_key
    try:
        with path.open("xb") as target:
            target.write(raw)
    except FileExistsError as exc:
        raise HTTPException(409, "Не удалось выделить безопасное хранилище для файла") from exc
    row = DealAttachment(
        id=attachment_id,
        booking_id=booking_id,
        filename=safe_name,
        content_type=safe_media_type(raw),
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
    try:
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    db.refresh(row)
    return {
        "id": row.id,
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "scan_status": row.scan_status,
        "downloadable": False,
    }


@router.get("/bookings/{booking_id}/attachments/{attachment_id}/download")
def download_booking_attachment(
    booking_id: str,
    attachment_id: str,
    request: HttpRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
):
    user = ctx.user
    if user.is_platform_admin:
        ensure_admin_2fa_session(request, db, user, ctx.session, force=True)
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")
    row = db.get(DealAttachment, attachment_id)
    if not row or row.booking_id != booking.id:
        raise HTTPException(404, "Вложение не найдено")
    if not attachment_is_downloadable(row):
        raise HTTPException(status.HTTP_409_CONFLICT, "Файл ожидает проверки безопасности")
    try:
        raw = read_verified_attachment(row)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise
        row.scan_status = "blocked"
        audit(
            db,
            actor_user_id=user.id,
            action="attachment.integrity_failed",
            entity_type="attachment",
            entity_id=row.id,
            payload={"booking_id": booking.id},
        )
        db.commit()
        raise
    return Response(
        content=raw,
        media_type=safe_media_type(raw),
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(row.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


def _deal_documents(
    version: OfferVersion,
    contract: Contract | None,
    attachments: list[DealAttachment] | None = None,
    *,
    contract_confirmed: bool = False,
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
                "label": "Черновик условий",
                "signed": contract_confirmed,
                "effect": contract.effect,
                "body_sha256": contract.body_sha256,
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
                "scan_status": attachment_effective_scan_status(att),
                "downloadable": attachment_is_downloadable(att),
            }
        )
    return docs


@router.get("/deal-room/{booking_id}")
def deal_room(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    if not (
        membership_ok(db, user, customer_org_id)
        or membership_ok(db, user, supplier_org_id)
    ):
        raise HTTPException(403, "Нет доступа")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.sequence.asc(), Message.created_at.asc(), Message.id.asc())
        .all()
    )
    version = db.get(OfferVersion, offer.active_version_id)
    contract = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    contract_signatures = (
        db.query(ContractSignature)
        .filter(ContractSignature.contract_id == contract.id)
        .order_by(ContractSignature.created_at, ContractSignature.id)
        .all()
        if contract else []
    )
    matching_signature_sides = {
        signature.side
        for signature in contract_signatures
        if contract
        and signature.offer_version_id == contract.offer_version_id
        and signature.body_sha256 == contract.body_sha256
        and signature.effect == contract.effect == "technical_draft_acknowledgement"
        and signature.actor_user_id
    }
    customer_draft_acknowledged = "customer" in matching_signature_sides
    supplier_draft_acknowledged = "supplier" in matching_signature_sides
    offer_acknowledgements = (
        db.query(OfferAcknowledgement)
        .filter(OfferAcknowledgement.offer_version_id == contract.offer_version_id)
        .order_by(OfferAcknowledgement.created_at, OfferAcknowledgement.id)
        .all()
        if contract and contract.offer_version_id else []
    )
    payments = (
        db.query(Payment)
        .filter(Payment.booking_id == booking.id)
        .order_by(Payment.created_at.asc(), Payment.id.asc())
        .all()
    )
    payment = payments[-1] if payments else None
    external_report = (
        db.query(ExternalPaymentReport)
        .filter_by(payment_id=payment.id)
        .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
        .first()
        if payment and payment.provider == "external"
        else None
    )
    external_events = (
        db.query(ExternalPaymentEvent)
        .filter_by(payment_id=payment.id)
        .order_by(ExternalPaymentEvent.created_at.asc(), ExternalPaymentEvent.id.asc())
        .all()
        if payment and payment.provider == "external"
        else []
    )
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
    cust_org = db.get(Organization, customer_org_id)
    sup_org = db.get(Organization, supplier_org_id)
    if x_booker_org == supplier_org_id and membership_ok(db, user, supplier_org_id):
        role = "supplier"
    else:
        role = "customer" if membership_ok(db, user, customer_org_id) else "supplier"
    workspace_kind = "customer" if role == "customer" else (sup_org.kind if sup_org else "artist")
    plan = db.query(PaymentPlan).filter_by(offer_version_id=version.id).one_or_none()
    obligations = (
        db.query(PaymentObligation)
        .filter_by(plan_id=plan.id)
        .order_by(PaymentObligation.created_at.asc(), PaymentObligation.id.asc())
        .all()
        if plan
        else []
    )
    obligation_payloads = [obligation_payload(row) for row in obligations]
    blocking_obligation = next(
        (row for row in obligation_payloads if row["blocks_check_in"]),
        None,
    )
    due_obligation = next(
        (
            row
            for row in obligation_payloads
            if row["effective_state"] in {"due", "overdue"}
            and row["status"] != "satisfied"
        ),
        None,
    )
    payment_action = (
        blocking_obligation or due_obligation
        if booking.status in {"AwaitingPayment", "Confirmed", "InProgress"}
        else None
    )
    return {
        "booking_id": booking.id,
        "offer_id": offer.id,
        "event_id": event.id,
        "requirement_id": getattr(req, "requirement_id", None),
        "status": booking.status,
        "role": role,
        "acting_org_id": customer_org_id if role == "customer" else supplier_org_id,
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
        "next_step": (
            "Погасить обязательный просроченный платёж"
            if blocking_obligation
            else _next_step(booking.status)
        ),
        "next_action": (
            {
                "kind": "pay_obligation",
                "obligation_id": payment_action["id"],
                "label": (
                    "Погасить просроченный платёж"
                    if payment_action["effective_state"] == "overdue"
                    else "Оплатить по графику"
                ),
            }
            if payment_action
            else {"kind": "booking_stage", "label": _next_step(booking.status)}
        ),
        "participants": [
            {
                "role": "customer",
                "name": conv.customer_name_snapshot or (cust_org.name if cust_org else "Заказчик"),
                "duty": "оплата и условия",
            },
            {
                "role": "supplier",
                "name": conv.supplier_name_snapshot or (sup_org.name if sup_org else "Исполнитель"),
                "duty": "дата и услуга",
            },
            {"role": "platform", "name": "Букер", "duty": "журнал и агрегатор, не исполнитель"},
        ],
        "hold": None
        if not hold
        else {"status": hold.status, "expires_at": hold.expires_at.isoformat()},
        "contract": None
        if not contract
        else {
            "id": contract.id,
            "customer_signed": customer_draft_acknowledged,
            "supplier_signed": supplier_draft_acknowledged,
            "body": contract.body,
            "body_sha256": contract.body_sha256,
            "offer_version_id": contract.offer_version_id,
            "template_version": contract.template_key,
            "legal_pack_version": contract.legal_pack_version,
            "effect": contract.effect,
            "acknowledgements": [
                {
                    "side": signature.side,
                    "organization_id": signature.organization_id,
                    "actor_user_id": signature.actor_user_id,
                    "actor_role_snapshot": signature.actor_role_snapshot,
                    "offer_version_id": signature.offer_version_id,
                    "body_sha256": signature.body_sha256,
                    "effect": signature.effect,
                    "created_at": signature.created_at.isoformat(),
                }
                for signature in contract_signatures
            ],
            "offer_acknowledgements": [
                {
                    "side": acknowledgement.side,
                    "organization_id": acknowledgement.organization_id,
                    "actor_user_id": acknowledgement.actor_user_id,
                    "actor_role_snapshot": acknowledgement.actor_role_snapshot,
                    "offer_version_id": acknowledgement.offer_version_id,
                    "created_at": acknowledgement.created_at.isoformat(),
                }
                for acknowledgement in offer_acknowledgements
            ],
            "otp_pending": not (
                customer_draft_acknowledged and supplier_draft_acknowledged
            ),
        },
        "documents": _deal_documents(
            version,
            contract,
            attachments,
            contract_confirmed=(
                customer_draft_acknowledged and supplier_draft_acknowledged
            ),
        ),
        "payment": None
        if not payment
        else {
            "id": payment.id,
            "obligation_id": payment.obligation_id,
            "status": payment.status,
            "amount_rub": payment.amount_rub,
            "provider": payment.provider,
            "evidence_version": payment.external_evidence_version or 0,
            "reliable_money_fact": False if payment.provider == "external" else None,
            "effective_evidence_state": (
                effective_review_state(external_events, external_report.status, external_report.id)
                if payment.provider == "external" and external_report else None
            ),
            "external_timeline": [
                {"event_id": row.id, "report_id": row.report_id, "kind": row.kind,
                 "at": row.created_at.isoformat()}
                for row in external_events
            ],
            "external_report": None if not external_report else {
                "id": external_report.id,
                "status": external_report.status,
                "review_note": external_report.review_note,
            },
        },
        "payments": [
            {
                "id": row.id,
                "obligation_id": row.obligation_id,
                "status": row.status,
                "amount_rub": row.amount_rub,
                "provider": row.provider,
            }
            for row in payments
        ],
        "payment_obligations": obligation_payloads,
        "quote": {
            "quote_id": version.id,
            "honorarium_rub": version.honorarium_rub,
            "commission_rate": version.commission_rate,
            "commission_rub": version.commission_rub,
            "total_rub": version.total_rub,
            "advance_rub": version.advance_rub,
            "balance_rub": version.balance_rub,
            "security_deposit_rub": version.security_deposit_rub,
            "payment_terms": version_payment_terms(version),
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
            _message_payload(m)
            for m in messages
        ],
    }


def _next_step(st: str) -> str:
    return {
        "Negotiation": "Подтвердить условия обеими сторонами",
        "DateHeld": "Технически подтвердить черновик условий",
        "AwaitingContract": "Технически подтвердить черновик условий",
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
    try:
        dispute_input = DisputeIn.model_validate(body)
    except ValueError as exc:
        raise HTTPException(400, "Выберите категорию спора из списка") from exc
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().one_or_none()
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    if membership_ok(db, user, customer_org_id):
        require_org_writer(db, user, customer_org_id)
    elif membership_ok(db, user, supplier_org_id):
        require_org_writer(db, user, supplier_org_id)
    else:
        raise HTTPException(403, "Нет доступа")
    dispute = create_dispute(
        db,
        booking=booking,
        category=dispute_input.category,
        notes=dispute_input.notes,
        actor_user_id=user.id,
    )
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
        entity_id=dispute.id,
        payload={
            "booking_id": booking.id,
            "category": dispute_input.category,
            "priority": dispute.priority,
            "response_due_at": dispute.response_due_at.isoformat(),
            "ai_decides": False,
        },
    )
    db.commit()
    db.refresh(dispute)
    return {**dispute_payload(db, dispute), "ai_decides": False}


@router.get("/bookings/{booking_id}/disputes")
def list_booking_disputes(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")
    rows = (
        db.query(Dispute)
        .filter(Dispute.booking_id == booking.id)
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
        .all()
    )
    return {"items": [dispute_payload(db, row) for row in rows]}


@router.post("/disputes/{dispute_id}/evidence")
def add_dispute_evidence(
    dispute_id: str,
    body: DisputeEvidenceIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    dispute = db.get(Dispute, dispute_id)
    if not dispute:
        raise HTTPException(404, "Спор не найден")
    booking = db.get(Booking, dispute.booking_id)
    if not booking:
        raise HTTPException(404, "Спор не найден")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if membership_ok(db, user, cust_org):
        require_org_writer(db, user, cust_org)
    elif membership_ok(db, user, sup_org):
        require_org_writer(db, user, sup_org)
    else:
        raise HTTPException(404, "Спор не найден")
    if dispute.status not in ACTIVE_DISPUTE_STATUSES:
        raise HTTPException(409, "Спор уже закрыт")
    attachment = db.get(DealAttachment, body.attachment_id)
    if not attachment or attachment.booking_id != booking.id:
        raise HTTPException(404, "Вложение этой брони не найдено")
    if not attachment_is_downloadable(attachment):
        raise HTTPException(409, "Доказательство доступно после безопасной проверки вложения")
    read_verified_attachment(attachment)
    existing = (
        db.query(DisputeEvidence)
        .filter(
            DisputeEvidence.dispute_id == dispute.id,
            DisputeEvidence.attachment_id == attachment.id,
        )
        .one_or_none()
    )
    if existing:
        return {"id": existing.id, "attachment_id": existing.attachment_id, "idempotent": True}
    evidence = DisputeEvidence(
        dispute_id=dispute.id,
        attachment_id=attachment.id,
        submitted_by_user_id=user.id,
        note=body.note.strip(),
    )
    db.add(evidence)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="dispute.evidence_added",
        entity_type="dispute",
        entity_id=dispute.id,
        payload={"attachment_id": attachment.id, "booking_id": booking.id},
    )
    db.commit()
    return {"id": evidence.id, "attachment_id": evidence.attachment_id, "idempotent": False}


@router.get("/requests/{request_id}/conversation")
def request_conversation(
    request_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    conv = db.query(Conversation).filter(Conversation.request_id == req.id).one_or_none()
    if not conv:
        raise HTTPException(404, "Диалог не найден")
    _req, customer_org_id, supplier_org_id = _require_conversation_access(db, user, conv)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.sequence.asc(), Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return {
        "conversation_id": conv.id,
        "request_id": req.id,
        "booking_id": conv.booking_id,
        "customer_org_id": customer_org_id,
        "supplier_org_id": supplier_org_id,
        "messages": [
            _message_payload(message)
            for message in messages
        ],
    }


@router.post("/requests/{request_id}/messages")
def post_request_message(
    request_id: str,
    body: MessageIn,
    request: HttpRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    messaging_limiter.check(client_key(request, "request-message"))
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    conv = db.query(Conversation).filter(Conversation.request_id == req.id).one_or_none()
    if not conv:
        raise HTTPException(404, "Диалог не найден")
    _req, customer_org_id, supplier_org_id = _require_conversation_access(db, user, conv)
    side, acting_org_id, member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=None,
        writer_required=True,
    )
    author_name = (
        conv.customer_name_snapshot if side == "customer" else conv.supplier_name_snapshot
    )
    text_body = body.body.strip()
    if not text_body:
        raise HTTPException(400, "body обязателен")
    if not body.idempotency_key:
        raise HTTPException(400, "idempotency_key обязателен")
    existing = (
        db.query(Message)
        .filter_by(conversation_id=conv.id, idempotency_key=body.idempotency_key)
        .one_or_none()
    )
    if existing:
        if not _message_replay_matches(
            existing,
            user_id=user.id,
            organization_id=acting_org_id,
            side=side,
            body=text_body,
        ):
            raise HTTPException(409, "Ключ повторного запроса использован с другими данными")
        return {"id": existing.id, "idempotent": True}
    message = Message(
        conversation_id=conv.id,
        author_user_id=user.id,
        author_org_id=acting_org_id,
        author_side=side,
        author_name_snapshot=author_name,
        actor_role_snapshot=member.role,
        attribution_status="attributed",
        kind="chat",
        body=text_body,
        idempotency_key=body.idempotency_key,
    )
    db.add(message)
    winning_message = _race_safe_message_flush(
        db,
        message,
        user_id=user.id,
        organization_id=acting_org_id,
        side=side,
        body=text_body,
    )
    if winning_message:
        return {"id": winning_message.id, "idempotent": True}
    audit(
        db,
        actor_user_id=user.id,
        action="request.message_sent",
        entity_type="request",
        entity_id=req.id,
        payload={
            "conversation_id": conv.id,
            "message_id": message.id,
            "organization_id": acting_org_id,
            "side": side,
        },
    )
    db.commit()
    return {"id": message.id, "idempotent": False}


@router.get("/messages/inbox")
def messages_inbox(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    """Message hub: deal-room threads the user can access (§19 / W4-MSG-HUB)."""
    from booker_api.models import TeamMember

    org_ids = [
        m.organization_id
        for m in db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    ]
    active_org_id = (x_booker_org or "").strip() or None
    if active_org_id and active_org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к выбранной организации")
    if not org_ids:
        return {"items": []}
    convs = db.query(Conversation).all()

    items: list[dict] = []
    activity_order: dict[str, tuple[float, str]] = {}
    for conv in convs:
        booking = db.get(Booking, conv.booking_id) if conv.booking_id else None
        req = _conversation_request(db, conv)
        if not req:
            continue
        cust_org, sup_org = conv.customer_org_id, conv.supplier_org_id
        if not cust_org or not sup_org:
            continue
        participant_orgs = [org_id for org_id in (cust_org, sup_org) if org_id in org_ids]
        if active_org_id:
            if active_org_id not in (cust_org, sup_org):
                continue
            viewer_org_id = active_org_id
        elif not participant_orgs:
            continue
        elif len(participant_orgs) > 1:
            raise HTTPException(409, "Выберите действующую организацию")
        else:
            viewer_org_id = participant_orgs[0]
        viewer_side = "customer" if viewer_org_id == cust_org else "supplier"
        can_write = (
            db.query(TeamMember)
            .filter(
                TeamMember.user_id == user.id,
                TeamMember.organization_id == viewer_org_id,
                TeamMember.role.in_(["owner", "admin", "manager"]),
            )
            .first()
            is not None
        )
        last = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.sequence.desc(), Message.created_at.desc(), Message.id.desc())
            .first()
        )
        received_at = (last.received_at or last.created_at) if last else None
        if received_at is not None:
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            activity_order[conv.id] = (received_at.timestamp(), conv.id)
        else:
            activity_order[conv.id] = (float("-inf"), conv.id)
        event = db.get(Event, req.event_id)
        read_state = (
            db.query(ConversationReadState)
            .filter_by(
                conversation_id=conv.id,
                user_id=user.id,
                organization_id=viewer_org_id,
            )
            .one_or_none()
        )
        unread_query = db.query(Message).filter(
            Message.conversation_id == conv.id,
            or_(Message.author_org_id.is_(None), Message.author_org_id != viewer_org_id),
        )
        if read_state:
            unread_query = unread_query.filter(Message.sequence > read_state.last_read_sequence)
        items.append(
            {
                "conversation_id": conv.id,
                "request_id": req.id,
                "request_status": req.status,
                "booking_id": booking.id if booking else None,
                "booking_status": booking.status if booking else None,
                "event_title": event.title if event else "",
                "customer_org": conv.customer_name_snapshot or cust_org,
                "supplier_org": conv.supplier_name_snapshot or sup_org,
                "deal_path": f"/deals/{booking.id}" if booking else None,
                "can_write": can_write,
                "viewer_org_id": viewer_org_id,
                "viewer_side": viewer_side,
                "unread_count": unread_query.count(),
                "last_message": (
                    {
                        "id": last.id,
                        "kind": last.kind,
                        "body": last.body[:240],
                        "author_side": last.author_side,
                        "author_name": last.author_name_snapshot,
                        "attribution_status": last.attribution_status,
                        "sequence": last.sequence,
                        "created_at": last.created_at.isoformat() if last.created_at else None,
                    }
                    if last
                    else None
                ),
            }
        )

    items.sort(key=lambda row: activity_order[row["conversation_id"]], reverse=True)
    return {"items": items[:50]}


@router.post("/conversations/{conversation_id}/read")
def mark_conversation_read(
    conversation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Диалог не найден")
    _req, customer_org_id, supplier_org_id = _require_conversation_access(db, user, conv)
    _side, acting_org_id, _member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=None,
        writer_required=False,
    )
    last_read_sequence = (
        db.query(func.max(Message.sequence))
        .filter(Message.conversation_id == conv.id)
        .scalar()
        or 0
    )
    read_at = now()
    values = {
        "id": str(uuid4()),
        "conversation_id": conv.id,
        "user_id": user.id,
        "organization_id": acting_org_id,
        "last_read_sequence": last_read_sequence,
        "read_at": read_at,
    }
    key_columns = [
        ConversationReadState.conversation_id,
        ConversationReadState.user_id,
        ConversationReadState.organization_id,
    ]
    if db.bind and db.bind.dialect.name == "postgresql":
        statement = postgresql_insert(ConversationReadState).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=key_columns,
            set_={
                "last_read_sequence": func.greatest(
                    ConversationReadState.last_read_sequence,
                    statement.excluded.last_read_sequence,
                ),
                "read_at": func.greatest(
                    ConversationReadState.read_at,
                    statement.excluded.read_at,
                ),
            },
        )
    else:
        statement = sqlite_insert(ConversationReadState).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=key_columns,
            set_={
                "last_read_sequence": func.max(
                    ConversationReadState.last_read_sequence,
                    statement.excluded.last_read_sequence,
                ),
                "read_at": func.max(
                    ConversationReadState.read_at,
                    statement.excluded.read_at,
                ),
            },
        )
    db.execute(statement)
    db.commit()
    state = (
        db.query(ConversationReadState)
        .filter_by(
            conversation_id=conv.id,
            user_id=user.id,
            organization_id=acting_org_id,
        )
        .one()
    )
    return {
        "conversation_id": conv.id,
        "organization_id": acting_org_id,
        "last_read_sequence": state.last_read_sequence,
        "read_at": state.read_at.isoformat(),
    }


@router.post("/deal-room/{booking_id}/messages")
def post_message(
    booking_id: str,
    body: MessageIn,
    request: HttpRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    messaging_limiter.check(client_key(request, "message"))
    conv = db.query(Conversation).filter(Conversation.booking_id == booking_id).one_or_none()
    if not conv:
        raise HTTPException(404, "Deal Room не найден")
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    _req, customer_org_id, supplier_org_id = _require_conversation_access(db, user, conv)
    side, acting_org_id, member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=None,
        writer_required=True,
    )
    author_name = (
        conv.customer_name_snapshot if side == "customer" else conv.supplier_name_snapshot
    )
    text_body = body.body.strip()
    if not text_body:
        raise HTTPException(400, "body обязателен")
    if not body.idempotency_key:
        raise HTTPException(400, "idempotency_key обязателен")
    existing = (
        db.query(Message)
        .filter_by(conversation_id=conv.id, idempotency_key=body.idempotency_key)
        .one_or_none()
    )
    if existing:
        if not _message_replay_matches(
            existing,
            user_id=user.id,
            organization_id=acting_org_id,
            side=side,
            body=text_body,
        ):
            raise HTTPException(409, "Ключ повторного запроса использован с другими данными")
        return {"id": existing.id, "idempotent": True}
    msg = Message(
        conversation_id=conv.id,
        author_user_id=user.id,
        author_org_id=acting_org_id,
        author_side=side,
        author_name_snapshot=author_name,
        actor_role_snapshot=member.role,
        attribution_status="attributed",
        kind="chat",
        body=text_body,
        idempotency_key=body.idempotency_key,
    )
    db.add(msg)
    winning_message = _race_safe_message_flush(
        db,
        msg,
        user_id=user.id,
        organization_id=acting_org_id,
        side=side,
        body=text_body,
    )
    if winning_message:
        return {"id": winning_message.id, "idempotent": True}
    audit(
        db,
        actor_user_id=user.id,
        action="deal.message_sent",
        entity_type="booking",
        entity_id=booking.id,
        payload={
            "conversation_id": conv.id,
            "message_id": msg.id,
            "organization_id": acting_org_id,
            "side": side,
        },
    )
    db.commit()
    return {"id": msg.id, "idempotent": False}


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
    if user.is_support_operator and not user.is_platform_admin:
        raise HTTPException(403, "Оператор поддержки не имеет доступа к сделке")
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    cust_org, sup_org = _booking_participant_orgs(db, booking)
    if not (membership_ok(db, user, cust_org) or membership_ok(db, user, sup_org)):
        raise HTTPException(403, "Нет доступа")

    def gen():
        yield f"data: {json.dumps({'status': booking.status})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
