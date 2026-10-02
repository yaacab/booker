"""Venue ownership claims + support/complaints (W4-CLAIM / W4-SUPPORT)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import and_, case, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import (
    AuditLog,
    Booking,
    Conversation,
    Event,
    Message,
    Offer,
    Organization,
    Payment,
    SessionToken,
    SupportAgentExchange,
    SupportAgentFeedback,
    SupportAgentSession,
    SupportMessage,
    SupportNotificationTarget,
    SupportOperatorNote,
    SupportTicket,
    TeamMember,
    User,
    Venue,
    VenueOwnershipClaim,
)
from booker_api.models import Request as DealRequest
from booker_api.rate_limit import (
    claim_limiter,
    messaging_limiter,
    support_agent_limiter,
    support_creation_limiter,
)
from booker_api.schemas import (
    SupportAgentEscalationIn,
    SupportAgentFeedbackIn,
    SupportAgentMessageIn,
    SupportAgentSessionIn,
    SupportMessageIn,
    SupportOperatorNoteIn,
    SupportTicketIn,
)
from booker_api.security import (
    audit,
    aware,
    current_user,
    now,
    require_admin_step_up,
    require_org_member,
    require_org_owner_or_admin_member,
    require_support_step_up,
)
from booker_api.support_agent import (
    answer_support_question,
    no_show_evidence_offset,
    redact_sensitive_support_text,
)
from booker_api.support_escalation import queue_new_ticket_notices
from booker_api.support_sla import support_response_due_at

router = APIRouter(tags=["trust"])

CLAIM_CATEGORIES = frozenset({"ownership", "correction", "duplicate"})
SUPPORT_REOPEN_WINDOW = timedelta(days=14)


class ClaimIn(BaseModel):
    organization_id: str | None = None
    evidence_note: str = Field(default="", max_length=4000)


class SupportAssignIn(BaseModel):
    action: str = Field(pattern="^(take|release|transfer|escalate)$")
    target_user_id: str | None = Field(default=None, max_length=36)


class SupportPriorityIn(BaseModel):
    priority: str = Field(pattern="^(normal|high|urgent)$")


class SupportOperatorRoleIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    enabled: bool


_SUPPORT_TARGET_SCHEDULE = (
    '{"timezone":"Europe/Moscow","weekdays":[0,1,2,3,4,5,6],'
    '"start":"10:00","end":"22:00"}'
)


class SupportTargetIn(BaseModel):
    recipient_user_id: str = Field(min_length=1, max_length=36)
    channel: str = Field(pattern="^(cabinet|email|telegram)$")
    escalation_level: str = Field(pattern="^(primary|backup|administrator)$")
    active: StrictBool


def _resolve_org(
    db: Session,
    user: User,
    organization_id: str | None,
    x_booker_org: str | None,
    *,
    required: bool = True,
) -> str | None:
    org_id = (organization_id or x_booker_org or user.active_organization_id or "").strip() or None
    if not org_id:
        if required:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужна организация")
        return None
    require_org_member(db, user, org_id)
    return org_id


@router.post("/venues/{venue_id}/claims", status_code=status.HTTP_201_CREATED)
def create_venue_claim(
    venue_id: str,
    body: ClaimIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")

    org_id = _resolve_org(db, user, body.organization_id, x_booker_org, required=True)
    assert org_id is not None
    require_org_owner_or_admin_member(db, user, org_id)
    claim_limiter.check(f"claim:u:{user.id}:org:{org_id}")
    org = db.get(Organization, org_id)
    if not org or org.kind != "venue":
        raise HTTPException(400, "Claim доступен только из организации площадки")

    # Never auto-grant ownership: claim stays pending for operator review.
    if venue.organization_id == org_id and venue.listing_origin == "owner":
        raise HTTPException(409, "Площадка уже закреплена за этой организацией")

    existing = (
        db.query(VenueOwnershipClaim)
        .filter(
            VenueOwnershipClaim.venue_id == venue_id,
            VenueOwnershipClaim.claimant_org_id == org_id,
            VenueOwnershipClaim.status == "pending",
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(409, "Заявка на владение уже на рассмотрении")

    row = VenueOwnershipClaim(
        venue_id=venue_id,
        claimant_user_id=user.id,
        claimant_org_id=org_id,
        evidence_note=(body.evidence_note or "").strip(),
        status="pending",
    )
    db.add(row)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="venue.claim.created",
        entity_type="venue_ownership_claim",
        entity_id=row.id,
        payload={
            "venue_id": venue_id,
            "listing_origin": venue.listing_origin,
            "grants_ownership": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "venue_id": row.venue_id,
        "status": row.status,
        "grants_ownership": False,
        "message": "Заявка принята. Владение не выдаётся сразу — нужна проверка.",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/venues/{venue_id}/claims")
def list_venue_claims(
    venue_id: str,
    user: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
):
    if not user.is_platform_admin:
        raise HTTPException(403, "Только оператор")
    rows = (
        db.query(VenueOwnershipClaim)
        .filter(VenueOwnershipClaim.venue_id == venue_id)
        .order_by(VenueOwnershipClaim.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "venue_id": r.venue_id,
                "claimant_org_id": r.claimant_org_id,
                "status": r.status,
                "evidence_note": r.evidence_note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            }
            for r in rows
        ]
    }


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _idempotency_hash(scope: str, actor_user_id: str, key: str) -> str:
    return hashlib.sha256(f"{scope}:{actor_user_id}:{key}".encode()).hexdigest()


def _ticket_payload(row: SupportTicket, *, include_body: bool = False) -> dict:
    result = {
        "id": row.id,
        "ticket_number": f"SUP-{row.id[:8].upper()}",
        "category": row.category,
        "subject": row.subject,
        "status": row.status,
        "priority": row.priority,
        "urgency_code": row.urgency_code,
        "response_due_at": aware(row.response_due_at).isoformat() if row.response_due_at else None,
        "state_version": row.state_version,
        "related_type": row.related_type,
        "related_id": row.related_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "reopened_at": row.reopened_at.isoformat() if row.reopened_at else None,
        "escalation": "human",
    }
    if include_body:
        result["body"] = row.body
    return result


def _message_payload(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "author_kind": row.author_kind,
        "body": row.body,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _note_payload(row: SupportOperatorNote) -> dict:
    return {
        "id": row.id,
        "author_user_id": row.author_user_id,
        "body": row.body,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _agent_exchange_payload(row: SupportAgentExchange) -> dict:
    try:
        source_ids = json.loads(row.source_ids_json)
    except (TypeError, ValueError):
        source_ids = []
    if not isinstance(source_ids, list):
        source_ids = []
    return {
        "id": row.id,
        "user_message": row.user_message,
        "assistant_message": row.assistant_message,
        "intent": row.intent,
        "outcome": row.outcome,
        "needs_human": row.needs_human,
        "source_ids": [item for item in source_ids if isinstance(item, str)],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "feedback": None,
    }


def _agent_session_payload(
    db: Session, row: SupportAgentSession, *, include_messages: bool = False
) -> dict:
    result = {
        "id": row.id,
        "status": row.status,
        "organization_id": row.organization_id,
        "related_type": row.related_type,
        "related_id": row.related_id,
        "ticket_id": row.ticket_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "escalated_at": row.escalated_at.isoformat() if row.escalated_at else None,
    }
    if include_messages:
        newest_messages = (
            db.query(SupportAgentExchange)
            .filter(SupportAgentExchange.session_id == row.id)
            .order_by(SupportAgentExchange.created_at.desc(), SupportAgentExchange.id.desc())
            .limit(100)
            .all()
        )
        messages = list(reversed(newest_messages))
        feedback_by_exchange = (
            {
                feedback.exchange_id: feedback
                for feedback in db.query(SupportAgentFeedback)
                .filter(
                    SupportAgentFeedback.exchange_id.in_([message.id for message in messages]),
                    SupportAgentFeedback.user_id == row.user_id,
                )
                .all()
            }
            if messages
            else {}
        )
        result["messages"] = []
        for message in messages:
            item = _agent_exchange_payload(message)
            feedback = feedback_by_exchange.get(message.id)
            if feedback:
                item["feedback"] = {"id": feedback.id, "rating": feedback.rating}
            result["messages"].append(item)
    return result


def _membership_org_ids(db: Session, user_id: str) -> set[str]:
    return {
        row.organization_id
        for row in db.query(TeamMember).filter(TeamMember.user_id == user_id).all()
    }


def _require_user_agent_session(
    db: Session, user: User, session_id: str
) -> SupportAgentSession:
    row = db.get(SupportAgentSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Сессия помощника не найдена")
    if row.organization_id and row.organization_id not in _membership_org_ids(db, user.id):
        raise HTTPException(404, "Сессия помощника не найдена")
    _resolve_support_relation(
        db,
        user,
        row.related_type,
        row.related_id,
        row.organization_id,
    )
    return row


def _request_participant_orgs(db: Session, request_row: DealRequest | None) -> set[str]:
    if not request_row:
        raise HTTPException(404, "Связанный объект не найден")
    conversation = (
        db.query(Conversation)
        .filter(Conversation.request_id == request_row.id)
        .one_or_none()
    )
    if conversation and conversation.customer_org_id and conversation.supplier_org_id:
        return {conversation.customer_org_id, conversation.supplier_org_id}
    event = db.get(Event, request_row.event_id)
    if not event:
        raise HTTPException(404, "Связанный объект не найден")
    return {event.organization_id, request_row.supplier_org_id}


def _booking_participant_orgs(db: Session, booking: Booking | None) -> set[str]:
    if not booking:
        raise HTTPException(404, "Связанный объект не найден")
    conversation = (
        db.query(Conversation).filter(Conversation.booking_id == booking.id).one_or_none()
    )
    if conversation and conversation.customer_org_id and conversation.supplier_org_id:
        return {conversation.customer_org_id, conversation.supplier_org_id}
    event = db.get(Event, booking.event_id)
    offer = db.get(Offer, booking.offer_id)
    request_row = db.get(DealRequest, offer.request_id) if offer else None
    if not event or not request_row or request_row.event_id != event.id:
        raise HTTPException(404, "Связанный объект не найден")
    return {event.organization_id, request_row.supplier_org_id}


def _conversation_participant_orgs(db: Session, conversation: Conversation | None) -> set[str]:
    if not conversation:
        raise HTTPException(404, "Связанный объект не найден")
    if not conversation.customer_org_id or not conversation.supplier_org_id:
        raise HTTPException(404, "Связанный объект не найден")
    return {conversation.customer_org_id, conversation.supplier_org_id}


def _resolve_support_relation(
    db: Session,
    user: User,
    related_type: str | None,
    related_id: str | None,
    organization_id: str | None,
) -> None:
    if related_type is None and related_id is None:
        return
    if related_type is None or related_id is None:
        raise HTTPException(422, "related_type и related_id передаются вместе")

    if related_type == "event":
        event = db.get(Event, related_id)
        participant_orgs = {event.organization_id} if event else set()
    elif related_type == "booking":
        participant_orgs = _booking_participant_orgs(db, db.get(Booking, related_id))
    elif related_type == "payment":
        payment = db.get(Payment, related_id)
        participant_orgs = (
            _booking_participant_orgs(db, db.get(Booking, payment.booking_id))
            if payment
            else set()
        )
    elif related_type == "message":
        message = db.get(Message, related_id)
        participant_orgs = (
            _conversation_participant_orgs(db, db.get(Conversation, message.conversation_id))
            if message
            else set()
        )
    else:
        raise HTTPException(422, "Недопустимый тип связанного объекта")

    member_orgs = _membership_org_ids(db, user.id)
    if not participant_orgs or not member_orgs.intersection(participant_orgs):
        raise HTTPException(404, "Связанный объект не найден")
    if organization_id and organization_id not in participant_orgs:
        raise HTTPException(404, "Связанный объект не найден")


def _ticket_user_access(db: Session, user: User, row: SupportTicket) -> bool:
    if row.author_user_id != user.id:
        return False
    return not (
        row.organization_id and row.organization_id not in _membership_org_ids(db, user.id)
    )


def _require_user_ticket(db: Session, user: User, ticket_id: str) -> SupportTicket:
    row = db.get(SupportTicket, ticket_id)
    if not row or not _ticket_user_access(db, user, row):
        raise HTTPException(404, "Обращение не найдено")
    return row


def _require_admin_ticket(db: Session, ticket_id: str) -> SupportTicket:
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    return row


def _ticket_messages(db: Session, ticket_id: str) -> list[SupportMessage]:
    return (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at.asc(), SupportMessage.id.asc())
        .all()
    )


def _cas_ticket_status(
    db: Session,
    row: SupportTicket,
    *,
    target: str,
    allowed_from: set[str],
    actor_user_id: str,
    action: str,
) -> bool:
    if row.status == target:
        unchanged = db.execute(
            update(SupportTicket)
            .where(
                SupportTicket.id == row.id,
                SupportTicket.state_version == row.state_version,
                SupportTicket.status == target,
            )
            .values(status=target)
            .execution_options(synchronize_session=False)
        )
        if unchanged.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Состояние обращения уже изменилось")
        db.commit()
        db.refresh(row)
        return False
    previous_status = row.status
    previous_version = row.state_version
    values: dict = {
        "status": target,
        "state_version": SupportTicket.state_version + 1,
    }
    transition_time = now()
    if target == "closed":
        values.update(closed_at=transition_time, closed_by_user_id=actor_user_id)
    elif target == "open":
        values.update(
            reopened_at=transition_time,
            closed_at=None,
            closed_by_user_id=None,
            accepted_by_user_id=None,
            accepted_at=None,
        )
    changed = db.execute(
        update(SupportTicket)
        .where(
            SupportTicket.id == row.id,
            SupportTicket.state_version == row.state_version,
            SupportTicket.status.in_(allowed_from),
        )
        .values(**values)
    )
    if changed.rowcount != 1:
        db.expire(row)
        db.refresh(row)
        raise HTTPException(409, "Состояние обращения уже изменилось")
    audit(
        db,
        actor_user_id=actor_user_id,
        action=action,
        entity_type="support_ticket",
        entity_id=row.id,
        payload={
            "from": previous_status,
            "to": target,
            "state_version": previous_version + 1,
        },
    )
    db.commit()
    db.refresh(row)
    return True


def _check_ticket_client_version(row: SupportTicket, expected: int) -> None:
    if row.state_version == expected:
        return
    raise HTTPException(409, "Состояние обращения уже изменилось")


def _create_support_message(
    db: Session,
    row: SupportTicket,
    actor: User,
    body: str,
    idempotency_key: str,
    *,
    author_kind: str,
    expected_version: int | None = None,
) -> SupportMessage:
    body = redact_sensitive_support_text(body)
    key_hash = _idempotency_hash(f"support-message:{row.id}", actor.id, idempotency_key)
    fingerprint = _fingerprint({"body": body, "author_kind": author_kind})
    existing = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == row.id,
            SupportMessage.author_user_id == actor.id,
            SupportMessage.idempotency_key_hash == key_hash,
        )
        .one_or_none()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency-Key уже использован с другим сообщением")
        return existing
    if expected_version is not None:
        _check_ticket_client_version(row, expected_version)
    if row.status in {"closed", "resolved"}:
        raise HTTPException(409, "Обращение закрыто. Сначала откройте его повторно")

    next_status = "waiting_for_support" if author_kind == "user" else "waiting_for_user"
    changed = db.execute(
        update(SupportTicket)
        .where(
            SupportTicket.id == row.id,
            SupportTicket.state_version == row.state_version,
            SupportTicket.status.in_({"open", "waiting_for_support", "waiting_for_user"}),
        )
        .values(
            status=next_status,
            state_version=SupportTicket.state_version + 1,
        )
    )
    if changed.rowcount != 1:
        replay = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.ticket_id == row.id,
                SupportMessage.author_user_id == actor.id,
                SupportMessage.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if replay:
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(409, "Idempotency-Key уже использован с другим сообщением")
            return replay
        db.expire(row)
        db.refresh(row)
        raise HTTPException(409, "Состояние обращения уже изменилось")

    message = SupportMessage(
        ticket_id=row.id,
        author_user_id=actor.id,
        author_kind=author_kind,
        body=body,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(message)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.ticket_id == row.id,
                SupportMessage.author_user_id == actor.id,
                SupportMessage.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if existing and existing.request_fingerprint == fingerprint:
            return existing
        raise HTTPException(409, "Idempotency-Key уже использован") from None
    audit(
        db,
        actor_user_id=actor.id,
        action="support.message.created",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={"message_id": message.id, "author_kind": author_kind},
    )
    db.commit()
    db.refresh(message)
    return message


@router.post("/support/assistant/sessions", status_code=status.HTTP_201_CREATED)
def create_support_agent_session(
    body: SupportAgentSessionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    org_id = _resolve_org(db, user, body.organization_id, x_booker_org, required=False)
    _resolve_support_relation(db, user, body.related_type, body.related_id, org_id)
    key_hash = _idempotency_hash("support-agent-session", user.id, idempotency_key)
    fingerprint = _fingerprint({**body.model_dump(mode="json"), "organization_id": org_id})
    existing = (
        db.query(SupportAgentSession)
        .filter(
            SupportAgentSession.user_id == user.id,
            SupportAgentSession.idempotency_key_hash == key_hash,
        )
        .one_or_none()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency-Key уже использован с другой сессией")
        return _agent_session_payload(db, existing, include_messages=True)

    support_creation_limiter.check(f"support-create:{user.id}")
    row = SupportAgentSession(
        user_id=user.id,
        organization_id=org_id,
        related_type=body.related_type,
        related_id=body.related_id,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportAgentSession)
            .filter(
                SupportAgentSession.user_id == user.id,
                SupportAgentSession.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if existing and existing.request_fingerprint == fingerprint:
            return _agent_session_payload(db, existing, include_messages=True)
        raise HTTPException(409, "Idempotency-Key уже использован") from None
    audit(
        db,
        actor_user_id=user.id,
        action="support.agent.session.created",
        entity_type="support_agent_session",
        entity_id=row.id,
        payload={"related_type": row.related_type, "has_organization": bool(org_id)},
    )
    db.commit()
    db.refresh(row)
    return _agent_session_payload(db, row, include_messages=True)


@router.get("/support/assistant/sessions/{session_id}")
def get_support_agent_session(
    session_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = _require_user_agent_session(db, user, session_id)
    return _agent_session_payload(db, row, include_messages=True)


@router.post(
    "/support/assistant/sessions/{session_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
def send_support_agent_message(
    session_id: str,
    body: SupportAgentMessageIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    row = _require_user_agent_session(db, user, session_id)
    key_hash = _idempotency_hash(f"support-agent-message:{row.id}", user.id, idempotency_key)
    safe_message = redact_sensitive_support_text(body.message)
    fingerprint = _fingerprint({"message": safe_message})
    existing = (
        db.query(SupportAgentExchange)
        .filter(
            SupportAgentExchange.session_id == row.id,
            SupportAgentExchange.idempotency_key_hash == key_hash,
        )
        .one_or_none()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            if existing.request_fingerprint != _fingerprint({"message": body.message}):
                raise HTTPException(409, "Idempotency-Key уже использован с другим сообщением")
            existing.request_fingerprint = fingerprint
            db.commit()
        return _agent_exchange_payload(existing)

    if row.status != "active":
        raise HTTPException(409, "Сессия уже передана специалисту или закрыта")
    support_agent_limiter.check(f"support-agent:{user.id}")
    reply = answer_support_question(body.message)
    claimed = db.execute(
        update(SupportAgentSession)
        .where(
            SupportAgentSession.id == row.id,
            SupportAgentSession.status == "active",
            SupportAgentSession.ticket_id.is_(None),
        )
        .values(updated_at=now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Сессия уже передана специалисту или закрыта")
    exchange = SupportAgentExchange(
        session_id=row.id,
        user_message=safe_message,
        assistant_message=reply.assistant_message,
        intent=reply.intent,
        outcome=reply.outcome,
        needs_human=reply.needs_human,
        source_ids_json=json.dumps(reply.source_ids, ensure_ascii=False),
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(exchange)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportAgentExchange)
            .filter(
                SupportAgentExchange.session_id == session_id,
                SupportAgentExchange.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if existing:
            if existing.request_fingerprint == fingerprint:
                return _agent_exchange_payload(existing)
            if existing.request_fingerprint == _fingerprint({"message": body.message}):
                existing.request_fingerprint = fingerprint
                db.commit()
                return _agent_exchange_payload(existing)
        raise HTTPException(409, "Idempotency-Key уже использован") from None
    audit(
        db,
        actor_user_id=user.id,
        action="support.agent.message.answered",
        entity_type="support_agent_session",
        entity_id=row.id,
        payload={
            "exchange_id": exchange.id,
            "intent": reply.intent,
            "outcome": reply.outcome,
            "source_ids": list(reply.source_ids),
        },
    )
    db.commit()
    db.refresh(exchange)
    return _agent_exchange_payload(exchange)


def _agent_escalation_category(intents: set[str]) -> str:
    if not intents:
        return "other"
    category_by_intent = {
        "event_day_no_show": "incident",
        "performer_cancelled_event": "incident",
        "duplicate_confirmed_booking": "incident",
        "paid_not_confirmed": "payment",
        "money_or_legal": "payment",
        "messages": "message",
        "media_upload": "media",
        "code_delivery": "profile",
        "account_access": "profile",
        "account_security": "profile",
        "organization_invitation": "profile",
        "supply_profile": "profile",
        "deal_documents": "technical",
        "arrival_unclear": "incident",
        "booking_flow": "brief",
        "technical": "technical",
    }
    for intent in (
        "account_security",
        "event_day_no_show",
        "performer_cancelled_event",
        "duplicate_confirmed_booking",
        "arrival_unclear",
        "paid_not_confirmed",
        "money_or_legal",
        "booking_flow",
        "technical",
        "messages",
        "media_upload",
        "code_delivery",
        "account_access",
        "organization_invitation",
        "supply_profile",
        "deal_documents",
    ):
        if intent in intents:
            return category_by_intent[intent]
    return "other"


def _support_urgency(intents: set[str]) -> tuple[str, str | None, int | None]:
    if "event_day_no_show" in intents:
        return "urgent", "event_day_no_show", 30
    if "paid_not_confirmed" in intents:
        return "high", "paid_not_confirmed", 120
    if intents.intersection({"account_security", "performer_cancelled_event",
                             "duplicate_confirmed_booking"}):
        # Route prominently, but do not invent a first-response SLA for these
        # cases until the support calendar/policy explicitly defines one.
        return "high", None, None
    return "normal", None, None


_NO_SHOW_RESOLVED = re.compile(
    r"(?:он|она|исполнитель|артист|фотограф)\s+приехал(?:а)?\s*[,;.!]\s*"
    r"помощь\s+больше\s+не\s+нужна\s*[.!]?",
    re.IGNORECASE,
)


def _active_agent_intents(exchanges: list[SupportAgentExchange]) -> set[str]:
    intents = {exchange.intent for exchange in exchanges}
    no_show_active = False
    for exchange in exchanges:
        if exchange.intent == "event_day_no_show":
            no_show_active = True
        elif _NO_SHOW_RESOLVED.fullmatch(exchange.user_message.strip()):
            no_show_active = False
    if not no_show_active:
        intents.discard("event_day_no_show")
    return intents


def _agent_escalation_body(exchanges: list[SupportAgentExchange], active_intents: set[str]) -> str:
    if not exchanges:
        return "Пользователь запросил помощь специалиста из помощника Букера."

    def excerpt(value: str, limit: int, *, preserve_no_show: bool = False) -> tuple[str, bool]:
        if len(value) <= limit:
            return value, False
        marker = " [середина сообщения пропущена] "
        first = (limit - len(marker)) // 3
        last = limit - len(marker) - first
        anchor_offset = no_show_evidence_offset(value) if preserve_no_show else None
        if anchor_offset is not None:
            head = tail = limit // 5
            middle_length = limit - head - tail - 2 * len(marker)
            start = max(
                head, min(anchor_offset - middle_length // 2, len(value) - tail - middle_length)
            )
            return (
                value[:head] + marker + value[start:start + middle_length] + marker + value[-tail:],
                True,
            )
        return value[:first] + marker + value[-last:], True

    urgent_index = next(
        (
            index
            for index in range(len(exchanges) - 1, -1, -1)
            if exchanges[index].intent == "event_day_no_show"
            and "event_day_no_show" in active_intents
        ),
        None,
    )
    if urgent_index is None:
        urgent_index = next(
            (
                index
                for index in range(len(exchanges) - 1, -1, -1)
                if exchanges[index].intent == "paid_not_confirmed"
                and "paid_not_confirmed" in active_intents
            ),
            None,
        )
    latest_index = len(exchanges) - 1
    selected = [latest_index]
    if urgent_index is not None and urgent_index != latest_index:
        selected.append(urgent_index)
    selected.extend(
        index
        for index in range(latest_index - 1, -1, -1)
        if index != urgent_index
    )
    parts = [f"Передача из помощника Букера. Сессия: {exchanges[-1].session_id}. Всего вопросов: {len(exchanges)}."]
    remaining = 8000 - len(parts[0]) - 100  # Keep room for omission notice.
    included = 0
    shortened = False
    for index in selected:
        item = exchanges[index]
        role = "Последний вопрос" if index == latest_index else (
            "Срочный вопрос ранее" if index == urgent_index else f"Предыдущий вопрос {index + 1}"
        )
        user_limit = 4000 if index == latest_index else (1500 if index == urgent_index else 800)
        answer_limit = 450 if index == latest_index else 250
        user_text, user_shortened = excerpt(
            item.user_message, user_limit, preserve_no_show=item.intent == "event_day_no_show"
        )
        answer_text, answer_shortened = excerpt(item.assistant_message, answer_limit)
        piece = f"{role} [{item.intent}]: {user_text}\nПомощник: {answer_text}"
        if len(piece) + 2 > remaining:
            continue
        parts.append(piece)
        remaining -= len(piece) + 2
        included += 1
        shortened = shortened or user_shortened or answer_shortened
    omitted = len(exchanges) - included
    if omitted or shortened:
        parts.append(
            f"История сокращена: пропущено вопросов: {omitted}; "
            "полный диалог сохранён в сессии помощника."
        )
    return "\n\n".join(parts)


@router.post("/support/assistant/sessions/{session_id}/escalate")
def escalate_support_agent_session(
    session_id: str,
    body: SupportAgentEscalationIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    row = _require_user_agent_session(db, user, session_id)
    key_hash = _idempotency_hash(f"support-agent-escalate:{row.id}", user.id, idempotency_key)
    fingerprint = _fingerprint({"reason_code": body.reason_code})
    if row.ticket_id:
        if (
            row.escalation_idempotency_key_hash != key_hash
            or row.escalation_request_fingerprint != fingerprint
        ):
            raise HTTPException(409, "Сессия уже передана специалисту")
        ticket = db.get(SupportTicket, row.ticket_id)
        if not ticket:
            raise HTTPException(409, "Не удалось найти созданное обращение")
        return {
            "session_id": row.id,
            "status": row.status,
            "ticket": _ticket_payload(ticket),
        }
    if row.status != "active":
        raise HTTPException(409, "Сессию нельзя передать из текущего состояния")

    locked = db.execute(
        update(SupportAgentSession)
        .where(
            SupportAgentSession.id == row.id,
            SupportAgentSession.status == "active",
            SupportAgentSession.ticket_id.is_(None),
        )
        .values(updated_at=now())
        .execution_options(synchronize_session=False)
    )
    if locked.rowcount != 1:
        db.rollback()
        current = _require_user_agent_session(db, user, session_id)
        if (
            current.ticket_id
            and current.escalation_idempotency_key_hash == key_hash
            and current.escalation_request_fingerprint == fingerprint
        ):
            ticket = db.get(SupportTicket, current.ticket_id)
            if ticket:
                return {"session_id": current.id, "status": current.status, "ticket": _ticket_payload(ticket)}
        raise HTTPException(409, "Сессия уже передана специалисту")
    exchanges = (
        db.query(SupportAgentExchange)
        .filter(SupportAgentExchange.session_id == row.id)
        .order_by(SupportAgentExchange.created_at.asc(), SupportAgentExchange.id.asc())
        .all()
    )
    if not exchanges:
        db.rollback()
        raise HTTPException(409, "Сначала опишите проблему помощнику")
    support_creation_limiter.check(f"support-create:{user.id}")
    active_intents = _active_agent_intents(exchanges)
    ticket_body = _agent_escalation_body(exchanges, active_intents)
    priority, urgency_code, response_minutes = _support_urgency(active_intents)
    ticket = SupportTicket(
        author_user_id=user.id,
        organization_id=row.organization_id,
        category=_agent_escalation_category(active_intents),
        subject="Обращение из помощника Букера",
        body=ticket_body,
        related_type=row.related_type,
        related_id=row.related_id,
        status="open",
        priority=priority,
        urgency_code=urgency_code,
        response_due_at=support_response_due_at(
            urgency_code, response_minutes, started_at=now()
        ),
        idempotency_key_hash=_idempotency_hash(
            "support-ticket", user.id, f"agent:{row.id}:{idempotency_key}"
        ),
        request_fingerprint=_fingerprint(
            {"session_id": row.id, "reason_code": body.reason_code, "body": ticket_body}
        ),
    )
    db.add(ticket)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        current = _require_user_agent_session(db, user, session_id)
        existing_ticket = db.get(SupportTicket, current.ticket_id) if current.ticket_id else None
        if (
            existing_ticket
            and current.escalation_idempotency_key_hash == key_hash
            and current.escalation_request_fingerprint == fingerprint
        ):
            return {
                "session_id": current.id,
                "status": current.status,
                "ticket": _ticket_payload(existing_ticket),
            }
        raise HTTPException(409, "Не удалось создать обращение повторно") from None
    initial_message = SupportMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_kind="user",
        body=ticket_body,
        idempotency_key_hash=_idempotency_hash(
            f"support-message:{ticket.id}", user.id, idempotency_key
        ),
        request_fingerprint=_fingerprint({"body": ticket_body, "author_kind": "user"}),
    )
    db.add(initial_message)
    escalation_time = now()
    claimed = db.execute(
        update(SupportAgentSession)
        .where(
            SupportAgentSession.id == row.id,
            SupportAgentSession.status == "active",
            SupportAgentSession.ticket_id.is_(None),
        )
        .values(
            status="escalated",
            ticket_id=ticket.id,
            escalated_at=escalation_time,
            updated_at=escalation_time,
            escalation_idempotency_key_hash=key_hash,
            escalation_request_fingerprint=fingerprint,
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        current = _require_user_agent_session(db, user, session_id)
        existing_ticket = db.get(SupportTicket, current.ticket_id) if current.ticket_id else None
        if (
            existing_ticket
            and current.escalation_idempotency_key_hash == key_hash
            and current.escalation_request_fingerprint == fingerprint
        ):
            return {
                "session_id": current.id,
                "status": current.status,
                "ticket": _ticket_payload(existing_ticket),
            }
        raise HTTPException(409, "Сессия уже передана специалисту")
    audit(
        db,
        actor_user_id=user.id,
        action="support.agent.escalated",
        entity_type="support_agent_session",
        entity_id=row.id,
        payload={
            "ticket_id": ticket.id,
            "reason_code": body.reason_code,
            "exchange_count": len(exchanges),
        },
    )
    queue_new_ticket_notices(db, ticket)
    db.commit()
    db.refresh(row)
    db.refresh(ticket)
    return {
        "session_id": row.id,
        "status": row.status,
        "ticket": _ticket_payload(ticket),
    }


@router.post("/support/assistant/exchanges/{exchange_id}/feedback")
def create_support_agent_feedback(
    exchange_id: str,
    body: SupportAgentFeedbackIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    exchange = db.get(SupportAgentExchange, exchange_id)
    row = (
        db.get(SupportAgentSession, exchange.session_id) if exchange else None
    )
    if not exchange or not row or row.user_id != user.id:
        raise HTTPException(404, "Ответ помощника не найден")
    _require_user_agent_session(db, user, row.id)
    safe_comment = redact_sensitive_support_text(body.comment)
    existing = (
        db.query(SupportAgentFeedback)
        .filter(
            SupportAgentFeedback.exchange_id == exchange.id,
            SupportAgentFeedback.user_id == user.id,
        )
        .one_or_none()
    )
    if existing:
        if (
            existing.rating != body.rating
            or existing.reason_code != body.reason_code
            or existing.comment != safe_comment
        ):
            raise HTTPException(409, "Оценка этого ответа уже сохранена")
        return {"id": existing.id, "rating": existing.rating}
    feedback = SupportAgentFeedback(
        exchange_id=exchange.id,
        user_id=user.id,
        rating=body.rating,
        reason_code=body.reason_code,
        comment=safe_comment,
    )
    db.add(feedback)
    audit(
        db,
        actor_user_id=user.id,
        action="support.agent.feedback.created",
        entity_type="support_agent_exchange",
        entity_id=exchange.id,
        payload={"rating": body.rating, "reason_code": body.reason_code},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportAgentFeedback)
            .filter(
                SupportAgentFeedback.exchange_id == exchange.id,
                SupportAgentFeedback.user_id == user.id,
            )
            .one_or_none()
        )
        if (
            existing
            and existing.rating == body.rating
            and existing.reason_code == body.reason_code
            and existing.comment == safe_comment
        ):
            return {"id": existing.id, "rating": existing.rating}
        raise HTTPException(409, "Оценка этого ответа уже сохранена") from None
    db.refresh(feedback)
    return {"id": feedback.id, "rating": feedback.rating}


@router.post("/support/tickets", status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    body: SupportTicketIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    org_id = _resolve_org(db, user, body.organization_id, x_booker_org, required=False)
    if org_id and org_id not in _membership_org_ids(db, user.id):
        raise HTTPException(403, "Нет доступа к организации")
    _resolve_support_relation(db, user, body.related_type, body.related_id, org_id)

    safe_subject = redact_sensitive_support_text(body.subject)[:255]
    safe_body = redact_sensitive_support_text(body.body)
    safe_request = {
        **body.model_dump(mode="json"),
        "subject": safe_subject,
        "body": safe_body,
        "organization_id": org_id,
    }
    classified = answer_support_question(f"{safe_subject} {safe_body}")
    priority, urgency_code, response_minutes = _support_urgency({classified.intent})
    key_hash = _idempotency_hash("support-ticket", user.id, idempotency_key)
    fingerprint = _fingerprint(safe_request)
    existing = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.author_user_id == user.id,
            SupportTicket.idempotency_key_hash == key_hash,
        )
        .one_or_none()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency-Key уже использован с другим обращением")
        return _ticket_payload(existing)

    support_creation_limiter.check(f"support-create:{user.id}")
    row = SupportTicket(
        author_user_id=user.id,
        organization_id=org_id,
        category=body.category,
        subject=safe_subject,
        body=safe_body,
        related_type=body.related_type,
        related_id=body.related_id,
        status="open",
        priority=priority,
        urgency_code=urgency_code,
        response_due_at=support_response_due_at(
            urgency_code, response_minutes, started_at=now()
        ),
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.author_user_id == user.id,
                SupportTicket.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if existing and existing.request_fingerprint == fingerprint:
            return _ticket_payload(existing)
        raise HTTPException(409, "Idempotency-Key уже использован") from None

    initial_message = SupportMessage(
        ticket_id=row.id,
        author_user_id=user.id,
        author_kind="user",
        body=safe_body,
        idempotency_key_hash=_idempotency_hash(
            f"support-message:{row.id}", user.id, idempotency_key
        ),
        request_fingerprint=_fingerprint({"body": safe_body, "author_kind": "user"}),
    )
    db.add(initial_message)
    audit(
        db,
        actor_user_id=user.id,
        action="support.ticket.created",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={"category": body.category, "related_type": row.related_type},
    )
    queue_new_ticket_notices(db, row)
    db.commit()
    db.refresh(row)
    return _ticket_payload(row)


@router.get("/support/tickets")
def list_my_support_tickets(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.author_user_id == user.id)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        .limit(100)
        .all()
    )
    return {"items": [_ticket_payload(row) for row in rows if _ticket_user_access(db, user, row)]}


@router.get("/support/tickets/{ticket_id}")
def get_support_ticket(
    ticket_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = _require_user_ticket(db, user, ticket_id)
    result = _ticket_payload(row, include_body=True)
    result["subject"] = redact_sensitive_support_text(result["subject"])
    result["messages"] = [_message_payload(message) for message in _ticket_messages(db, row.id)]
    return result


@router.post("/support/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def reply_support_ticket(
    ticket_id: str,
    body: SupportMessageIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    messaging_limiter.check(f"support-message:{user.id}")
    row = _require_user_ticket(db, user, ticket_id)
    message = _create_support_message(
        db,
        row,
        user,
        body.body,
        idempotency_key,
        author_kind="user",
    )
    return _message_payload(message)


@router.post("/support/tickets/{ticket_id}/close")
def close_support_ticket(
    ticket_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_user_ticket(db, user, ticket_id)
    _check_ticket_client_version(row, expected_version)
    _cas_ticket_status(
        db,
        row,
        target="closed",
        allowed_from={"open", "waiting_for_support", "waiting_for_user", "resolved"},
        actor_user_id=user.id,
        action="support.ticket.closed",
    )
    return {"id": row.id, "status": row.status, "state_version": row.state_version}


@router.post("/support/tickets/{ticket_id}/reopen")
def reopen_support_ticket(
    ticket_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_user_ticket(db, user, ticket_id)
    _check_ticket_client_version(row, expected_version)
    if row.status == "open":
        _cas_ticket_status(
            db,
            row,
            target="open",
            allowed_from={"closed"},
            actor_user_id=user.id,
            action="support.ticket.reopened",
        )
        return {"id": row.id, "status": row.status, "state_version": row.state_version}
    if row.status != "closed" or not row.closed_at:
        raise HTTPException(409, "Повторное открытие недоступно из текущего состояния")
    if now() - aware(row.closed_at) > SUPPORT_REOPEN_WINDOW:
        raise HTTPException(409, "Срок повторного открытия истёк")
    _cas_ticket_status(
        db,
        row,
        target="open",
        allowed_from={"closed"},
        actor_user_id=user.id,
        action="support.ticket.reopened",
    )
    return {"id": row.id, "status": row.status, "state_version": row.state_version}


@router.get("/admin/support/operators")
def admin_list_support_operators(
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
):
    rows = (db.query(User).filter(User.is_support_operator.is_(True))
            .order_by(User.id).all())
    audit(db, actor_user_id=admin.id, action="support.operators.viewed",
          entity_type="user", entity_id=admin.id, payload={"count": len(rows)})
    db.commit()
    return {"items": [{"id": row.id, "email": row.email,
                       "totp_enabled": row.totp_enabled,
                       "email_verified": bool(row.email_verified_at)} for row in rows]}


@router.post("/admin/support/operators")
def admin_set_support_operator(
    body: SupportOperatorRoleIn,
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
):
    email = body.email.strip().lower()
    target = db.query(User).filter(User.email == email).with_for_update().one_or_none()
    if not target:
        raise HTTPException(404, "Аккаунт не найден")
    if target.is_platform_admin:
        raise HTTPException(409, "Администратору платформы отдельная роль не нужна")
    if body.enabled and not target.email_verified_at:
        raise HTTPException(409, "Сначала подтвердите email оператора")
    if body.enabled and db.query(TeamMember.id).filter(TeamMember.user_id == target.id).first():
        raise HTTPException(409, "Для оператора нужен отдельный аккаунт без участия в организациях")
    if target.is_support_operator == body.enabled:
        return {"id": target.id, "is_support_operator": body.enabled,
                "totp_enabled": target.totp_enabled, "idempotent": True}
    target.is_support_operator = body.enabled
    # Any bearer issued before the role change must not inherit staff access.
    db.query(SessionToken).filter(SessionToken.user_id == target.id).delete(
        synchronize_session=False
    )
    audit(db, actor_user_id=admin.id,
          action="support.operator.granted" if body.enabled else "support.operator.revoked",
          entity_type="user", entity_id=target.id,
          payload={"email_hash": hashlib.sha256(email.encode()).hexdigest()})
    db.commit()
    return {"id": target.id, "is_support_operator": body.enabled,
            "totp_enabled": target.totp_enabled, "idempotent": False}


@router.get("/admin/support/notification-targets")
def admin_list_support_notification_targets(
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
):
    rows = (db.query(SupportNotificationTarget)
            .order_by(SupportNotificationTarget.escalation_level,
                      SupportNotificationTarget.channel,
                      SupportNotificationTarget.recipient_user_id)
            .limit(100).all())
    audit(db, actor_user_id=admin.id, action="support.targets.viewed",
          entity_type="user", entity_id=admin.id, payload={"count": len(rows)})
    db.commit()
    return {"items": [{"id": row.id, "recipient_user_id": row.recipient_user_id,
                       "channel": row.channel, "escalation_level": row.escalation_level,
                       "active": row.active, "schedule": json.loads(row.schedule_json),
                       "state_version": row.state_version} for row in rows],
            "email_transport_ready": settings.email_provider == "smtp" and bool(settings.email_smtp_host),
            "telegram_transport_ready": False}


@router.post("/admin/support/notification-targets")
def admin_set_support_notification_target(
    body: SupportTargetIn,
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    recipient = (db.query(User).filter(User.id == body.recipient_user_id)
                 .with_for_update().one_or_none())
    if not recipient or not recipient.email_verified_at or not recipient.totp_enabled:
        raise HTTPException(409, "Адресат должен подтвердить почту и подключить 2FA")
    if body.escalation_level == "administrator":
        if not recipient.is_platform_admin:
            raise HTTPException(409, "Административный сигнал требует администратора")
    elif not recipient.is_support_operator or recipient.is_platform_admin:
        raise HTTPException(409, "Основной или резервный адресат должен быть оператором")
    if body.active and body.channel == "telegram":
        raise HTTPException(409, "Telegram адресат не подтверждён и транспорт выключен")
    if body.active and body.channel == "email" and (
        settings.email_provider != "smtp" or not settings.email_smtp_host
    ):
        raise HTTPException(409, "Рабочий email транспорт пока не настроен")
    row = (db.query(SupportNotificationTarget).filter(
        SupportNotificationTarget.recipient_user_id == recipient.id,
        SupportNotificationTarget.channel == body.channel,
        SupportNotificationTarget.escalation_level == body.escalation_level,
    ).with_for_update().one_or_none())
    if row:
        if row.state_version != expected_version:
            raise HTTPException(409, "Настройка адресата уже изменилась")
        if row.active == body.active:
            return {"id": row.id, "active": row.active,
                    "state_version": row.state_version, "idempotent": True}
        try:
            changed = db.execute(update(SupportNotificationTarget).where(
                SupportNotificationTarget.id == row.id,
                SupportNotificationTarget.state_version == expected_version,
            ).values(active=body.active, updated_at=now(),
                     state_version=SupportNotificationTarget.state_version + 1)).rowcount
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Основной или резервный адресат уже назначен") from None
        if changed != 1:
            db.rollback()
            raise HTTPException(409, "Настройка адресата уже изменилась")
        target_id = row.id
        version = expected_version + 1
    else:
        if expected_version != 0:
            raise HTTPException(409, "Новая настройка начинается с версии 0")
        row = SupportNotificationTarget(
            recipient_user_id=recipient.id, channel=body.channel,
            escalation_level=body.escalation_level, active=body.active,
            schedule_json=_SUPPORT_TARGET_SCHEDULE,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Адресат или уровень уже занят") from None
        target_id = row.id
        version = 0
    audit(db, actor_user_id=admin.id,
          action="support.target.configured",
          entity_type="support_notification_target", entity_id=target_id,
          payload={"recipient_user_id": recipient.id, "channel": body.channel,
                   "escalation_level": body.escalation_level, "active": body.active,
                   "state_version": version})
    db.commit()
    return {"id": target_id, "active": body.active,
            "state_version": version, "idempotent": False}


@router.get("/admin/support/tickets")
def admin_list_support_tickets(
    state: str = Query(default="all", pattern="^(all|active|open|waiting_for_support|waiting_for_user|resolved|closed)$"),
    overdue_only: bool = False,
    escalated_only: bool = False,
    priority: str | None = Query(default=None, pattern="^(urgent|high|normal)$"),
    category: str | None = Query(default=None, pattern="^[a-z_]{1,64}$"),
    assigned_to_me: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10000),
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
):
    query = db.query(SupportTicket)
    if state == "active":
        query = query.filter(SupportTicket.status.notin_({"closed", "resolved"}))
    elif state != "all":
        query = query.filter(SupportTicket.status == state)
    priority_order = case(
        (SupportTicket.priority == "urgent", 0),
        (SupportTicket.priority == "high", 1),
        else_=2,
    )
    current_time = now()
    operator_responded = (
        db.query(SupportMessage.id)
        .filter(
            SupportMessage.ticket_id == SupportTicket.id,
            SupportMessage.author_kind == "operator",
        )
        .exists()
    )
    overdue_condition = and_(
        SupportTicket.response_due_at.is_not(None),
        SupportTicket.response_due_at <= current_time,
        SupportTicket.status.notin_({"closed", "resolved"}),
        ~operator_responded,
    )
    open_count = db.query(func.count(SupportTicket.id)).filter(
        SupportTicket.status.notin_({"closed", "resolved"})
    ).scalar() or 0
    overdue_count = db.query(func.count(SupportTicket.id)).filter(overdue_condition).scalar() or 0
    if overdue_only:
        query = query.filter(overdue_condition)
    if escalated_only:
        query = query.filter(SupportTicket.overdue_escalated_at.is_not(None))
    if priority:
        query = query.filter(SupportTicket.priority == priority)
    if category:
        query = query.filter(SupportTicket.category == category)
    if assigned_to_me:
        query = query.filter(SupportTicket.assigned_to_user_id == admin.id)
    total = query.order_by(None).count()
    rows = (
        query.order_by(
            case((overdue_condition, 0), else_=1).asc(),
            priority_order.asc(),
            SupportTicket.response_due_at.asc(),
            SupportTicket.created_at.asc(),
            SupportTicket.id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    ids = [row.id for row in rows]
    first_response_times = (
        {
            ticket_id: first_at
            for ticket_id, first_at in db.query(
                SupportMessage.ticket_id, func.min(SupportMessage.created_at)
            )
            .filter(
                SupportMessage.ticket_id.in_(ids),
                SupportMessage.author_kind == "operator",
            )
            .group_by(SupportMessage.ticket_id)
            .all()
        }
        if ids
        else set()
    )
    audit(
        db,
        actor_user_id=admin.id,
        action="support.admin.queue.viewed",
        entity_type="user",
        entity_id=admin.id,
        payload={"state": state, "overdue_only": overdue_only,
                 "limit": limit, "offset": offset},
    )
    db.commit()
    items = []
    for row in rows:
        item = _ticket_payload(row)
        item["subject"] = " ".join(redact_sensitive_support_text(row.subject).split())[:120]
        item["assigned_to_user_id"] = row.assigned_to_user_id
        item["accepted_by_user_id"] = row.accepted_by_user_id
        item["accepted_at"] = aware(row.accepted_at).isoformat() if row.accepted_at else None
        item["has_operator_response"] = row.id in first_response_times
        item["response_overdue"] = bool(
            row.response_due_at
            and aware(row.response_due_at) <= current_time
            and row.status not in {"closed", "resolved"}
            and row.id not in first_response_times
        )
        item["overdue_escalated_at"] = (
            aware(row.overdue_escalated_at).isoformat()
            if row.overdue_escalated_at else None
        )
        first_response = first_response_times.get(row.id)
        item["first_response_late"] = bool(
            row.response_due_at
            and first_response
            and aware(first_response) > aware(row.response_due_at)
        )
        items.append(item)
    return {"items": items, "total": total, "open_count": int(open_count),
            "overdue_count": int(overdue_count), "limit": limit, "offset": offset}


@router.get("/admin/support/staff")
def support_staff_for_handoff(
    actor: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
):
    """Expose only eligible staff identities, not their private contact details."""
    rows = (
        db.query(User)
        .filter(
            (User.is_support_operator.is_(True) | User.is_platform_admin.is_(True)),
            User.email_verified_at.is_not(None),
            User.totp_enabled.is_(True),
        )
        .order_by(User.full_name, User.id)
        .all()
    )
    audit(db, actor_user_id=actor.id, action="support.staff.viewed",
          entity_type="user", entity_id=actor.id, payload={"count": len(rows)})
    db.commit()
    return {"items": [{"id": row.id, "name": row.full_name,
                       "role": "administrator" if row.is_platform_admin else "operator"}
                      for row in rows]}


@router.get("/admin/support/tickets/{ticket_id}")
def admin_get_support_ticket(
    ticket_id: str,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
):
    row = _require_admin_ticket(db, ticket_id)
    result = _ticket_payload(row, include_body=True)
    result["subject"] = redact_sensitive_support_text(result["subject"])
    result["body"] = redact_sensitive_support_text(result["body"])
    result["assigned_to_user_id"] = row.assigned_to_user_id
    result["accepted_by_user_id"] = row.accepted_by_user_id
    result["accepted_at"] = aware(row.accepted_at).isoformat() if row.accepted_at else None
    result["overdue_escalated_at"] = (
        aware(row.overdue_escalated_at).isoformat() if row.overdue_escalated_at else None
    )
    messages = _ticket_messages(db, row.id)
    actors = {message.author_user_id for message in messages}
    actor_names = {actor.id: actor.full_name for actor in db.query(User).filter(User.id.in_(actors)).all()}
    result["messages"] = [
        {**_message_payload(message), "body": redact_sensitive_support_text(message.body),
         "actor_user_id": message.author_user_id,
         "actor_name": actor_names.get(message.author_user_id, "Участник")}
        for message in messages
    ]
    system_actions = {
        "support.ticket.created", "support.ticket.closed", "support.ticket.reopened",
        "support.admin.ticket.closed", "support.admin.ticket.reopened",
        "support.admin.ticket.assigned", "support.admin.ticket.released",
        "support.admin.ticket.accepted",
        "support.admin.ticket.transferred", "support.admin.ticket.escalated",
        "support.admin.ticket.priority_changed",
        "support.ticket.first_response_overdue",
    }
    events = db.query(AuditLog).filter(
        AuditLog.entity_type == "support_ticket", AuditLog.entity_id == row.id,
        AuditLog.action.in_(system_actions),
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(201).all()
    result["system_events_truncated"] = len(events) > 200
    result["system_events"] = [
        {"id": event.id, "action": event.action, "actor_user_id": event.actor_user_id,
         "created_at": event.created_at.isoformat()}
        for event in reversed(events[:200])
    ]
    audit(
        db,
        actor_user_id=admin.id,
        action="support.admin.ticket.viewed",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={},
    )
    db.commit()
    return result


@router.post("/admin/support/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def admin_reply_support_ticket(
    ticket_id: str,
    body: SupportMessageIn,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    expected_version: int | None = Header(default=None, alias="If-Match", ge=0),
):
    messaging_limiter.check(f"support-admin-message:{admin.id}")
    row = _require_admin_ticket(db, ticket_id)
    message = _create_support_message(
        db,
        row,
        admin,
        body.body,
        idempotency_key,
        author_kind="operator",
        expected_version=expected_version,
    )
    return {**_message_payload(message), "actor_user_id": message.author_user_id}


@router.post("/admin/support/tickets/{ticket_id}/assign")
def admin_assign_support_ticket(
    ticket_id: str,
    body: SupportAssignIn,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_admin_ticket(db, ticket_id)
    _check_ticket_client_version(row, expected_version)
    if row.status in {"closed", "resolved"}:
        raise HTTPException(409, "Закрытое обращение нельзя назначить")
    if body.action in {"take", "release"} and body.target_user_id is not None:
        raise HTTPException(422, "Цель доступна только для передачи обращения")
    if body.action in {"transfer", "escalate"}:
        if not body.target_user_id:
            raise HTTPException(422, "Выберите сотрудника для передачи")
        target = (db.query(User).filter(User.id == body.target_user_id)
                  .with_for_update().one_or_none())
        if not target or not target.email_verified_at or not target.totp_enabled or not (
            target.is_support_operator or target.is_platform_admin
        ):
            raise HTTPException(409, "Сотрудник больше не может принимать обращения")
        if body.action == "escalate" and not target.is_platform_admin:
            raise HTTPException(422, "Эскалацию может принять только администратор")
        if not admin.is_platform_admin and row.assigned_to_user_id != admin.id:
            raise HTTPException(403, "Передать можно только своё обращение")
        assignee = target.id
    elif body.action == "take":
        if row.assigned_to_user_id and row.assigned_to_user_id != admin.id:
            raise HTTPException(409, "Обращение уже назначено другому сотруднику")
        assignee = admin.id
    else:
        if (row.assigned_to_user_id and row.assigned_to_user_id != admin.id
                and not admin.is_platform_admin):
            raise HTTPException(403, "Снять можно только своё назначение")
        assignee = None
    needs_acceptance = body.action == "take" and (
        row.accepted_by_user_id != admin.id or row.accepted_at is None
    )
    if row.assigned_to_user_id == assignee and not needs_acceptance:
        return {"id": row.id, "assigned_to_user_id": assignee,
                "accepted_by_user_id": row.accepted_by_user_id,
                "accepted_at": aware(row.accepted_at).isoformat() if row.accepted_at else None,
                "state_version": row.state_version, "idempotent": True}
    previous_assignee = row.assigned_to_user_id
    acceptance_time = now() if body.action == "take" else None
    changed = db.execute(
        update(SupportTicket).where(
            SupportTicket.id == row.id,
            SupportTicket.state_version == expected_version,
            SupportTicket.status.notin_({"closed", "resolved"}),
        ).values(assigned_to_user_id=assignee,
                 accepted_by_user_id=admin.id if body.action == "take" else None,
                 accepted_at=acceptance_time,
                 state_version=SupportTicket.state_version + 1)
    ).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "Состояние обращения уже изменилось")
    action = {
        "take": "support.admin.ticket.assigned",
        "release": "support.admin.ticket.released",
        "transfer": "support.admin.ticket.transferred",
        "escalate": "support.admin.ticket.escalated",
    }[body.action]
    if previous_assignee != assignee:
        audit(db, actor_user_id=admin.id, action=action,
              entity_type="support_ticket", entity_id=row.id,
              payload={"from_user_id": previous_assignee, "assigned_to_user_id": assignee})
    if body.action == "take":
        audit(db, actor_user_id=admin.id, action="support.admin.ticket.accepted",
              entity_type="support_ticket", entity_id=row.id,
              payload={"accepted_by_user_id": admin.id, "assigned_to_user_id": assignee})
    db.commit()
    return {"id": row.id, "assigned_to_user_id": assignee,
            "accepted_by_user_id": admin.id if body.action == "take" else None,
            "accepted_at": acceptance_time.isoformat() if acceptance_time else None,
            "state_version": expected_version + 1}


@router.post("/admin/support/tickets/{ticket_id}/priority")
def admin_change_support_priority(
    ticket_id: str,
    body: SupportPriorityIn,
    actor: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_admin_ticket(db, ticket_id)
    _check_ticket_client_version(row, expected_version)
    if row.status in {"closed", "resolved"}:
        raise HTTPException(409, "Приоритет закрытого обращения не меняется")
    if row.priority == body.priority:
        return {"id": row.id, "priority": row.priority,
                "state_version": row.state_version, "idempotent": True}
    previous = row.priority
    changed = db.execute(
        update(SupportTicket).where(
            SupportTicket.id == row.id,
            SupportTicket.state_version == expected_version,
            SupportTicket.status.notin_({"closed", "resolved"}),
        ).values(priority=body.priority, state_version=SupportTicket.state_version + 1)
    ).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "Состояние обращения уже изменилось")
    audit(db, actor_user_id=actor.id, action="support.admin.ticket.priority_changed",
          entity_type="support_ticket", entity_id=row.id,
          payload={"from": previous, "to": body.priority,
                   "response_deadline_unchanged": True})
    db.commit()
    return {"id": row.id, "priority": body.priority,
            "state_version": expected_version + 1}


@router.get("/admin/support/tickets/{ticket_id}/notes")
def admin_list_support_notes(
    ticket_id: str,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
):
    row = _require_admin_ticket(db, ticket_id)
    notes = (
        db.query(SupportOperatorNote)
        .filter(SupportOperatorNote.ticket_id == row.id)
        .order_by(SupportOperatorNote.created_at.asc(), SupportOperatorNote.id.asc())
        .all()
    )
    audit(
        db,
        actor_user_id=admin.id,
        action="support.admin.notes.viewed",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={},
    )
    db.commit()
    return {"items": [{**_note_payload(note), "body": redact_sensitive_support_text(note.body)}
                      for note in notes]}


@router.post("/admin/support/tickets/{ticket_id}/notes", status_code=status.HTTP_201_CREATED)
def admin_create_support_note(
    ticket_id: str,
    body: SupportOperatorNoteIn,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    row = _require_admin_ticket(db, ticket_id)
    safe_body = redact_sensitive_support_text(body.body)
    key_hash = _idempotency_hash(f"support-note:{row.id}", admin.id, idempotency_key)
    fingerprint = _fingerprint({"body": safe_body})
    existing = (
        db.query(SupportOperatorNote)
        .filter(
            SupportOperatorNote.ticket_id == row.id,
            SupportOperatorNote.author_user_id == admin.id,
            SupportOperatorNote.idempotency_key_hash == key_hash,
        )
        .one_or_none()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency-Key уже использован с другой заметкой")
        return _note_payload(existing)

    note = SupportOperatorNote(
        ticket_id=row.id,
        author_user_id=admin.id,
        body=safe_body,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(note)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SupportOperatorNote)
            .filter(
                SupportOperatorNote.ticket_id == row.id,
                SupportOperatorNote.author_user_id == admin.id,
                SupportOperatorNote.idempotency_key_hash == key_hash,
            )
            .one_or_none()
        )
        if existing and existing.request_fingerprint == fingerprint:
            return _note_payload(existing)
        raise HTTPException(409, "Idempotency-Key уже использован") from None
    audit(
        db,
        actor_user_id=admin.id,
        action="support.admin.note.created",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={"note_id": note.id},
    )
    db.commit()
    db.refresh(note)
    return _note_payload(note)


@router.post("/admin/support/tickets/{ticket_id}/close")
def admin_close_support_ticket(
    ticket_id: str,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_admin_ticket(db, ticket_id)
    _check_ticket_client_version(row, expected_version)
    _cas_ticket_status(
        db,
        row,
        target="closed",
        allowed_from={"open", "waiting_for_support", "waiting_for_user", "resolved"},
        actor_user_id=admin.id,
        action="support.admin.ticket.closed",
    )
    return {"id": row.id, "status": row.status, "state_version": row.state_version}


@router.post("/admin/support/tickets/{ticket_id}/reopen")
def admin_reopen_support_ticket(
    ticket_id: str,
    admin: User = Depends(require_support_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _require_admin_ticket(db, ticket_id)
    _check_ticket_client_version(row, expected_version)
    if row.status == "open":
        _cas_ticket_status(
            db,
            row,
            target="open",
            allowed_from={"closed"},
            actor_user_id=admin.id,
            action="support.admin.ticket.reopened",
        )
        return {"id": row.id, "status": row.status, "state_version": row.state_version}
    if row.status != "closed":
        raise HTTPException(409, "Повторное открытие недоступно из текущего состояния")
    _cas_ticket_status(
        db,
        row,
        target="open",
        allowed_from={"closed"},
        actor_user_id=admin.id,
        action="support.admin.ticket.reopened",
    )
    return {"id": row.id, "status": row.status, "state_version": row.state_version}
