"""Публичные брифы и отклики поставщиков (E18 / E19 / W3-BRIEF)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, BriefResponse, Event, Organization, PublicBrief, User, utcnow
from booker_api.security import audit, current_user, membership, require_org_writer

router = APIRouter(tags=["briefs"])

GUEST_COUNT_BANDS = {"1-50", "51-100", "101-200", "200+"}
PUBLIC_BRIEF_KEYS = {
    "id",
    "organization_id",
    "title",
    "city",
    "date_from",
    "date_to",
    "role_needed",
    "guest_count_band",
    "public_notes",
    "status",
    "created_at",
    "closed_at",
}
# Never exposed on public brief payloads (private event / PII).
FORBIDDEN_PUBLIC_KEYS = {
    "phone",
    "email",
    "budget",
    "budget_rub",
    "guest_count",
    "notes",
    "event_id",
    "created_by_user_id",
}


class BriefPublishIn(BaseModel):
    organization_id: str
    title: str = Field(..., min_length=1, max_length=255)
    city: str = Field(default="Москва", max_length=128)
    date_from: datetime
    date_to: datetime
    role_needed: str = Field(..., min_length=1, max_length=64)
    guest_count_band: str = Field(default="1-50", max_length=32)
    public_notes: str = ""
    event_id: str | None = None


class BriefRespondIn(BaseModel):
    supplier_org_id: str
    message: str = Field(default="", max_length=4000)


@router.get("/brief-responses/mine")
def my_brief_responses(organization_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not _membership_ok(db, user, organization_id):
        raise HTTPException(403, "Нет доступа к откликам")
    rows = db.query(BriefResponse).filter(BriefResponse.supplier_org_id == organization_id).order_by(BriefResponse.created_at.desc()).all()
    return {"items": [{**_response_out(row), "brief": _brief_public(brief)} for row in rows if (brief := db.get(PublicBrief, row.brief_id)) is not None]}


def _membership_ok(db: Session, user: User, org_id: str) -> bool:
    return bool(membership(db, user.id, org_id) or user.is_platform_admin)


def _brief_public(row: PublicBrief) -> dict:
    payload = {
        "id": row.id,
        "organization_id": row.organization_id,
        "title": row.title,
        "city": row.city,
        "date_from": row.date_from.isoformat() if row.date_from else None,
        "date_to": row.date_to.isoformat() if row.date_to else None,
        "role_needed": row.role_needed,
        "guest_count_band": row.guest_count_band,
        "public_notes": row.public_notes,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
    }
    leaked = FORBIDDEN_PUBLIC_KEYS & set(payload)
    if leaked:
        raise HTTPException(500, "Утечка приватных полей в публичном брифе")
    assert set(payload) <= PUBLIC_BRIEF_KEYS
    return payload


def _response_out(row: BriefResponse) -> dict:
    return {
        "id": row.id,
        "brief_id": row.brief_id,
        "supplier_org_id": row.supplier_org_id,
        "author_user_id": row.author_user_id,
        "message": row.message,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _guest_band_ok(band: str) -> str:
    value = (band or "").strip()
    if value not in GUEST_COUNT_BANDS:
        raise HTTPException(
            400,
            f"guest_count_band должен быть одним из: {', '.join(sorted(GUEST_COUNT_BANDS))}",
        )
    return value


@router.post("/briefs")
def publish_brief(
    body: BriefPublishIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_writer(db, user, body.organization_id)
    org = db.get(Organization, body.organization_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if org.kind != "customer" and not user.is_platform_admin:
        raise HTTPException(403, "Публиковать бриф может только заказчик")

    date_from = body.date_from
    date_to = body.date_to
    if date_to < date_from:
        raise HTTPException(400, "date_to не может быть раньше date_from")

    event_id = body.event_id
    if event_id:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(404, "Событие не найдено")
        if event.organization_id != body.organization_id and not user.is_platform_admin:
            raise HTTPException(403, "Событие принадлежит другой организации")

    title = body.title.strip()
    if not title:
        raise HTTPException(400, "title обязателен")
    role = body.role_needed.strip().lower()
    if not role:
        raise HTTPException(400, "role_needed обязателен")

    row = PublicBrief(
        organization_id=body.organization_id,
        created_by_user_id=user.id,
        event_id=event_id,
        title=title,
        city=(body.city or "Москва").strip() or "Москва",
        date_from=date_from,
        date_to=date_to,
        role_needed=role,
        guest_count_band=_guest_band_ok(body.guest_count_band),
        public_notes=(body.public_notes or "").strip(),
        status="open",
    )
    db.add(row)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="brief.published",
        entity_type="public_brief",
        entity_id=row.id,
        payload={
            "organization_id": body.organization_id,
            "role_needed": role,
            "has_event_link": bool(event_id),
        },
    )
    db.commit()
    db.refresh(row)
    return _brief_public(row)


@router.get("/briefs")
def list_briefs(
    status: str = Query("open"),
    role_needed: str | None = Query(None),
    city: str | None = Query(None),
    organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Публичный список открытых брифов; фильтры по роли/городу/владельцу."""
    q = db.query(PublicBrief)
    st = (status or "open").strip().lower()
    if st != "all":
        q = q.filter(PublicBrief.status == st)
    if role_needed:
        q = q.filter(PublicBrief.role_needed == role_needed.strip().lower())
    if city:
        q = q.filter(PublicBrief.city == city.strip())
    if organization_id:
        q = q.filter(PublicBrief.organization_id == organization_id)
    rows = q.order_by(PublicBrief.created_at.desc()).all()
    return {"items": [_brief_public(r) for r in rows]}


@router.get("/briefs/{brief_id}")
def get_brief(brief_id: str, db: Session = Depends(get_db)):
    row = db.get(PublicBrief, brief_id)
    if not row:
        raise HTTPException(404, "Бриф не найден")
    return _brief_public(row)


@router.post("/briefs/{brief_id}/close")
def close_brief(
    brief_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PublicBrief, brief_id)
    if not row:
        raise HTTPException(404, "Бриф не найден")
    require_org_writer(db, user, row.organization_id)
    if row.status == "closed":
        return _brief_public(row)
    row.status = "closed"
    row.closed_at = utcnow()
    audit(
        db,
        actor_user_id=user.id,
        action="brief.closed",
        entity_type="public_brief",
        entity_id=row.id,
        payload={},
    )
    db.commit()
    db.refresh(row)
    return _brief_public(row)


@router.post("/briefs/{brief_id}/responses")
def respond_to_brief(
    brief_id: str,
    body: BriefRespondIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    brief = db.get(PublicBrief, brief_id)
    if not brief:
        raise HTTPException(404, "Бриф не найден")
    if brief.status != "open":
        raise HTTPException(409, "Бриф закрыт")

    require_org_writer(db, user, body.supplier_org_id)
    supplier = db.get(Organization, body.supplier_org_id)
    if not supplier:
        raise HTTPException(404, "Организация не найдена")
    if supplier.kind not in {"artist", "venue"} and not user.is_platform_admin:
        raise HTTPException(403, "Откликаться могут артист или площадка")
    if body.supplier_org_id == brief.organization_id:
        raise HTTPException(403, "Нельзя откликаться на свой бриф")

    existing = (
        db.query(BriefResponse)
        .filter(
            BriefResponse.brief_id == brief.id,
            BriefResponse.supplier_org_id == body.supplier_org_id,
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(409, "Отклик этой организации уже есть")

    row = BriefResponse(
        brief_id=brief.id,
        supplier_org_id=body.supplier_org_id,
        author_user_id=user.id,
        message=(body.message or "").strip(),
        status="interested",
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Отклик этой организации уже есть") from exc

    audit(
        db,
        actor_user_id=user.id,
        action="brief.response_created",
        entity_type="brief_response",
        entity_id=row.id,
        payload={"brief_id": brief.id, "supplier_org_id": body.supplier_org_id},
    )
    db.commit()
    db.refresh(row)
    # Does not create Request / Offer / Booking.
    return _response_out(row)


@router.get("/briefs/{brief_id}/responses")
def list_brief_responses(
    brief_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    brief = db.get(PublicBrief, brief_id)
    if not brief:
        raise HTTPException(404, "Бриф не найден")
    if not _membership_ok(db, user, brief.organization_id):
        raise HTTPException(403, "Нет доступа")
    rows = (
        db.query(BriefResponse)
        .filter(BriefResponse.brief_id == brief.id)
        .order_by(BriefResponse.created_at.desc())
        .all()
    )
    items = []
    for row in rows:
        supplier = db.get(Organization, row.supplier_org_id)
        artist = db.query(Artist).filter(Artist.organization_id == row.supplier_org_id).first()
        items.append({**_response_out(row), "supplier_name": supplier.name if supplier else "Артист", "artist_id": artist.id if artist else None})
    return {"items": items}
