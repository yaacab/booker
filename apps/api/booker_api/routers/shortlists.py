"""Shared shortlists + compare (E22 / W3-SHARE / W3-COMPARE)."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import (
    Artist,
    Favorite,
    SharedShortlist,
    SharedShortlistItem,
    User,
    Venue,
    VenueHall,
    utcnow,
)
from booker_api.security import audit, aware, current_user, require_org_member

router = APIRouter(tags=["shortlists"])

ALLOWED_TYPES = frozenset({"artist", "venue"})


class ShortlistCreateIn(BaseModel):
    organization_id: str | None = None
    target_type: str
    title: str = "Подборка"
    favorite_ids: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    ttl_days: int = Field(default=14, ge=1, le=90)

    @field_validator("target_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in ALLOWED_TYPES:
            raise ValueError("target_type: artist|venue")
        return normalized


def _org_id(db: Session, user: User, organization_id: str | None, x_booker_org: str | None) -> str:
    org_id = (organization_id or x_booker_org or user.active_organization_id or "").strip()
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужна организация")
    require_org_member(db, user, org_id)
    return org_id


def _snapshot(db: Session, target_type: str, target_id: str) -> tuple[str, str, str]:
    if target_type == "artist":
        row = db.get(Artist, target_id)
        if not row:
            raise HTTPException(404, "Артист не найден")
        summary = f"категория: {row.category}" if getattr(row, "category", None) else ""
        return row.name, row.city or "", summary
    row = db.get(Venue, target_id)
    if not row:
        raise HTTPException(404, "Площадка не найдена")
    halls = db.query(VenueHall).filter(VenueHall.venue_id == row.id).all()
    cap = max([h.capacity for h in halls], default=row.capacity)
    summary = f"вместимость до {cap}"
    return row.name, row.city or "", summary


def _shortlist_out(row: SharedShortlist, *, include_token: bool = False) -> dict:
    items = sorted(row.items, key=lambda i: i.sort_order)
    data = {
        "id": row.id,
        "title": row.title,
        "target_type": row.target_type,
        "organization_id": row.organization_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "items": [
            {
                "target_id": it.target_id,
                "name": it.name,
                "city": it.city,
                "summary": it.summary,
            }
            for it in items
        ],
        "share_path": f"/s/{row.token}",
        "active": row.revoked_at is None and aware(row.expires_at) > utcnow(),
    }
    if include_token:
        data["token"] = row.token
    return data


@router.post("/shortlists", status_code=status.HTTP_201_CREATED)
def create_shortlist(
    body: ShortlistCreateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _org_id(db, user, body.organization_id, x_booker_org)
    favs = (
        db.query(Favorite)
        .filter(
            Favorite.id.in_(body.favorite_ids),
            Favorite.user_id == user.id,
            Favorite.organization_id == org_id,
            Favorite.target_type == body.target_type,
        )
        .all()
    )
    if len(favs) != len(set(body.favorite_ids)):
        raise HTTPException(400, "Некоторые favorite_ids не найдены в избранном")
    if not (2 <= len(favs) <= 4):
        raise HTTPException(400, "В подборку нужно 2–4 кандидата одного типа")

    token = secrets.token_urlsafe(24)
    row = SharedShortlist(
        owner_user_id=user.id,
        organization_id=org_id,
        target_type=body.target_type,
        title=(body.title or "Подборка").strip()[:255] or "Подборка",
        token=token,
        expires_at=utcnow() + timedelta(days=body.ttl_days),
    )
    db.add(row)
    db.flush()
    for idx, fav in enumerate(favs):
        name, city, summary = _snapshot(db, fav.target_type, fav.target_id)
        db.add(
            SharedShortlistItem(
                shortlist_id=row.id,
                target_id=fav.target_id,
                name=name,
                city=city,
                summary=summary,
                sort_order=idx,
            )
        )
    audit(
        db,
        actor_user_id=user.id,
        action="shortlist.created",
        entity_type="shared_shortlist",
        entity_id=row.id,
        payload={"target_type": body.target_type, "items": len(favs)},
    )
    db.commit()
    db.refresh(row)
    return _shortlist_out(row, include_token=True)


@router.post("/shortlists/{shortlist_id}/revoke")
def revoke_shortlist(
    shortlist_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SharedShortlist, shortlist_id)
    if not row or row.owner_user_id != user.id:
        raise HTTPException(404, "Подборка не найдена")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        audit(
            db,
            actor_user_id=user.id,
            action="shortlist.revoked",
            entity_type="shared_shortlist",
            entity_id=row.id,
            payload={},
        )
        db.commit()
        db.refresh(row)
    return _shortlist_out(row, include_token=True)


@router.get("/shared/{token}")
def public_shared_shortlist(token: str, db: Session = Depends(get_db)):
    row = db.query(SharedShortlist).filter(SharedShortlist.token == token).one_or_none()
    if not row or row.revoked_at is not None or aware(row.expires_at) <= utcnow():
        raise HTTPException(404, "Ссылка недоступна")
    # Public payload: no phones, private budget, chat, owner identity
    return {
        "title": row.title,
        "target_type": row.target_type,
        "expires_at": row.expires_at.isoformat(),
        "items": [
            {
                "target_id": it.target_id,
                "name": it.name,
                "city": it.city,
                "summary": it.summary,
                "profile_path": f"/{'artists' if row.target_type == 'artist' else 'venues'}/{it.target_id}",
            }
            for it in sorted(row.items, key=lambda i: i.sort_order)
        ],
        "robots": "noindex",
    }


@router.get("/compare")
def compare_candidates(
    target_type: str = Query(...),
    ids: str = Query(..., description="Comma-separated 2–4 ids"),
    db: Session = Depends(get_db),
):
    normalized = target_type.strip().lower()
    if normalized not in ALLOWED_TYPES:
        raise HTTPException(400, "target_type: artist|venue")
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    if not (2 <= len(id_list) <= 4):
        raise HTTPException(400, "Нужно 2–4 id")
    if len(set(id_list)) != len(id_list):
        raise HTTPException(400, "Дубликаты id")

    columns: list[dict] = []
    if normalized == "artist":
        for aid in id_list:
            artist = db.get(Artist, aid)
            if not artist:
                raise HTTPException(404, f"Артист {aid} не найден")
            columns.append(
                {
                    "id": artist.id,
                    "name": artist.name,
                    "city": artist.city or "неизвестно",
                    "category": getattr(artist, "category", None) or "неизвестно",
                    "verified": bool(artist.verified),
                    "capacity": None,
                    "honorarium_hint": "по запросу",
                }
            )
    else:
        for vid in id_list:
            venue = db.get(Venue, vid)
            if not venue:
                raise HTTPException(404, f"Площадка {vid} не найдена")
            halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
            max_cap = max([h.capacity for h in halls], default=venue.capacity)
            columns.append(
                {
                    "id": venue.id,
                    "name": venue.name,
                    "city": venue.city or "неизвестно",
                    "category": "venue",
                    "verified": bool(venue.verified),
                    "capacity": max_cap if max_cap else "неизвестно",
                    "honorarium_hint": "по запросу",
                }
            )

    fields = ["name", "city", "category", "verified", "capacity", "honorarium_hint"]
    return {
        "target_type": normalized,
        "fields": fields,
        "columns": columns,
        "note": "Поля без данных помечены как «неизвестно»; цены — только серверный ориентир.",
    }
