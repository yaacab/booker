"""Venue ownership claims + support/complaints (W4-CLAIM / W4-SUPPORT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Organization, SupportTicket, User, Venue, VenueOwnershipClaim, utcnow
from booker_api.security import audit, current_user, require_org_member

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


@router.post("/support/tickets", status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    body: SupportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _resolve_org(db, user, body.organization_id, x_booker_org, required=False)
    row = SupportTicket(
        author_user_id=user.id,
        organization_id=org_id,
        category=body.category,
        subject=body.subject.strip(),
        body=body.body.strip(),
        related_type=(body.related_type or "").strip() or None,
        related_id=(body.related_id or "").strip() or None,
        status="open",
    )
    db.add(row)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="support.ticket.created",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={"category": body.category, "related_type": row.related_type},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "ticket_number": f"SUP-{row.id[:8].upper()}",
        "category": row.category,
        "subject": row.subject,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "escalation": "human",
    }


@router.get("/support/tickets")
def list_my_support_tickets(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(SupportTicket)
    if not user.is_platform_admin:
        q = q.filter(SupportTicket.author_user_id == user.id)
    rows = q.order_by(SupportTicket.created_at.desc()).limit(100).all()
    return {
        "items": [
            {
                "id": r.id,
                "ticket_number": f"SUP-{r.id[:8].upper()}",
                "category": r.category,
                "subject": r.subject,
                "status": r.status,
                "related_type": r.related_type,
                "related_id": r.related_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/support/tickets/{ticket_id}/close")
def close_support_ticket(
    ticket_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    if row.author_user_id != user.id and not user.is_platform_admin:
        raise HTTPException(403, "Нет доступа")
    row.status = "closed"
    audit(
        db,
        actor_user_id=user.id,
        action="support.ticket.closed",
        entity_type="support_ticket",
        entity_id=row.id,
        payload={},
    )
    db.commit()
    return {"id": row.id, "status": row.status}
