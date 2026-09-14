"""Venue ownership claims + support/complaints (W4-CLAIM / W4-SUPPORT)."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.commerce.entitlements import get_entitlements
from booker_api.db import get_db
from booker_api.models import (
    Organization,
    SupportReply,
    SupportTicket,
    User,
    Venue,
    VenueOwnershipClaim,
)
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import (
    AuthContext,
    audit,
    auth_context,
    current_user,
    ensure_admin_2fa_session,
    require_org_member,
)

router = APIRouter(tags=["trust"])

CLAIM_CATEGORIES = frozenset({"ownership", "correction", "duplicate"})
SUPPORT_CATEGORIES = frozenset(
    {
        "profile",
        "brief",
        "message",
        "review",
        "media",
        "payment",
        "technical",
        "other",
    }
)


class ClaimIn(BaseModel):
    organization_id: str | None = None
    evidence_note: str = Field(default="", max_length=4000)


class SupportIn(BaseModel):
    organization_id: str | None = None
    category: str
    subject: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=3, max_length=8000)
    related_type: str | None = Field(default=None, max_length=32)
    related_id: str | None = Field(default=None, max_length=36)

    @field_validator("subject", "body")
    @classmethod
    def strip_text(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Введите не менее трёх символов")
        return value.strip()

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in SUPPORT_CATEGORIES:
            raise ValueError("category: " + "|".join(sorted(SUPPORT_CATEGORIES)))
        return normalized


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
    user: User = Depends(current_user),
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


def support_user(request: Request, ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)):
    if ctx.user.is_platform_admin:
        ensure_admin_2fa_session(request, db, ctx.user, ctx.session)
    return ctx.user


def ticket_payload(row, detail=False):
    result = {"id": row.id, "ticket_number": f"SUP-{row.id[:8].upper()}",
        "category": row.category, "subject": row.subject, "status": row.status,
        "priority": row.priority, "related_type": row.related_type, "related_id": row.related_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "escalation": "human"}
    if detail:
        result["body"] = row.body
    return result


@router.post("/support/tickets", status_code=status.HTTP_201_CREATED)
def create_support_ticket(body: SupportIn, user: User = Depends(support_user), db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128)):
    org_id = _resolve_org(db, user, body.organization_id, x_booker_org, required=False)
    messaging_limiter.check(f"support-create:{user.id}")
    key = hashlib.sha256(f"{user.id}:{idempotency_key}".encode()).hexdigest() if idempotency_key else None
    fingerprint = hashlib.sha256(json.dumps({**body.model_dump(), "organization_id": org_id}, sort_keys=True).encode()).hexdigest()

    def reuse(row):
        if row.request_fingerprint != fingerprint:
            raise HTTPException(409, "Содержимое обращения изменилось. Отправьте его как новое")
        return ticket_payload(row)

    if key:
        existing = db.query(SupportTicket).filter_by(idempotency_key=key).one_or_none()
        if existing:
            return reuse(existing)
    priority = bool(org_id and get_entitlements(db, org_id)["features"].get("support.priority"))
    row = SupportTicket(author_user_id=user.id, organization_id=org_id, category=body.category,
        subject=body.subject, body=body.body, related_type=(body.related_type or "").strip() or None,
        related_id=(body.related_id or "").strip() or None, status="open", priority=priority,
        idempotency_key=key, request_fingerprint=fingerprint)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(SupportTicket).filter_by(idempotency_key=key).one_or_none() if key else None
        if existing:
            return reuse(existing)
        raise
    audit(db, actor_user_id=user.id, action="support.ticket.created", entity_type="support_ticket",
        entity_id=row.id, payload={"category": body.category, "related_type": row.related_type, "priority": priority})
    db.commit(); db.refresh(row)
    return ticket_payload(row)


@router.get("/support/tickets")
def list_my_support_tickets(user: User = Depends(support_user), db: Session = Depends(get_db),
    state: str = Query(default="all", pattern="^(all|open|closed)$"), offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100)):
    analytics_limiter.check(f"support-list:{user.id}")
    q = db.query(SupportTicket)
    if not user.is_platform_admin:
        q = q.filter(SupportTicket.author_user_id == user.id)
    if state != "all":
        q = q.filter(SupportTicket.status == state)
    total = q.count()
    if user.is_platform_admin:
        # Open before closed, priority before standard, FIFO within each queue.
        q = q.order_by(case((SupportTicket.status == "open", 0), else_=1), SupportTicket.priority.desc(), SupportTicket.created_at, SupportTicket.id)
        audit(db, actor_user_id=user.id, action="support.queue.viewed", entity_type="user", entity_id=user.id, payload={"state": state})
    else:
        q = q.order_by(SupportTicket.created_at.desc(), SupportTicket.id)
    rows = q.offset(offset).limit(limit).all()
    result = {"items": [ticket_payload(row) for row in rows], "total": total, "offset": offset, "is_operator": user.is_platform_admin}
    db.commit()
    return result


@router.get("/support/tickets/{ticket_id}")
def support_ticket_detail(ticket_id: str, user: User = Depends(support_user), db: Session = Depends(get_db)):
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    if row.author_user_id != user.id and not user.is_platform_admin:
        raise HTTPException(403, "Нет доступа")
    analytics_limiter.check(f"support-detail:{user.id}")
    audit(db, actor_user_id=user.id, action="support.ticket.viewed", entity_type="support_ticket", entity_id=row.id, payload={})
    db.commit()
    return ticket_payload(row, detail=True)


@router.post("/support/tickets/{ticket_id}/close")
def close_support_ticket(ticket_id: str, user: User = Depends(support_user), db: Session = Depends(get_db)):
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    if row.author_user_id != user.id and not user.is_platform_admin:
        raise HTTPException(403, "Нет доступа")
    messaging_limiter.check(f"support-close:{user.id}")
    changed = db.execute(update(SupportTicket).where(SupportTicket.id == row.id, SupportTicket.status != "closed").values(status="closed"))
    if changed.rowcount:
        audit(db, actor_user_id=user.id, action="support.ticket.closed", entity_type="support_ticket", entity_id=row.id, payload={})
    db.commit()
    return {"id": row.id, "status": "closed"}


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)

    @field_validator("body")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Введите текст ответа")
        return value.strip()


def reply_payload(row):
    return {"id": row.id, "author_role": row.author_role, "body": row.body, "created_at": row.created_at.isoformat()}


def reply_ticket(db, user, ticket_id):
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    if row.author_user_id != user.id and not user.is_platform_admin:
        raise HTTPException(403, "Нет доступа")
    return row


@router.get("/support/tickets/{ticket_id}/messages")
def support_messages(ticket_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(support_user), db: Session = Depends(get_db)):
    ticket = reply_ticket(db, user, ticket_id)
    analytics_limiter.check(f"support-messages:{user.id}")
    q = db.query(SupportReply).filter_by(ticket_id=ticket.id)
    total = q.count()
    rows = q.order_by(SupportReply.created_at.desc(), SupportReply.id.desc()).offset(offset).limit(limit).all()
    result = {"items": [reply_payload(row) for row in reversed(rows)], "total": total, "offset": offset, "can_reply": ticket.status == "open"}
    audit(db, actor_user_id=user.id, action="support.messages.viewed", entity_type="support_ticket", entity_id=ticket.id, payload={})
    db.commit()
    return result


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
def send_support_message(ticket_id: str, body: ReplyIn, user: User = Depends(support_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128)):
    ticket = reply_ticket(db, user, ticket_id)
    messaging_limiter.check(f"support-reply:{user.id}")
    # Serialize with concurrent replies and ticket closure, including on SQLite.
    db.execute(update(SupportTicket).where(SupportTicket.id == ticket.id).values(status=SupportTicket.status))
    db.refresh(ticket)
    key = hashlib.sha256(f"{ticket.id}:{user.id}:{idempotency_key}".encode()).hexdigest()
    existing = db.query(SupportReply).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if existing.body != body.body:
            raise HTTPException(409, "Текст ответа изменился. Отправьте его как новый")
        return reply_payload(existing)
    if ticket.status != "open":
        raise HTTPException(409, "Обращение закрыто. Для нового вопроса создайте обращение")
    row = SupportReply(ticket_id=ticket.id, author_user_id=user.id,
        author_role="operator" if user.is_platform_admin else "author", body=body.body, idempotency_key=key)
    db.add(row); db.flush()
    audit(db, actor_user_id=user.id, action="support.message.created", entity_type="support_ticket", entity_id=ticket.id,
        payload={"message_id": row.id, "author_role": row.author_role})
    db.commit(); db.refresh(row)
    return reply_payload(row)
