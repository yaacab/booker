"""Избранное артистов и площадок. Добавление ≠ заявка/hold/бронь (E04)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, Favorite, User, Venue
from booker_api.security import current_user, membership, require_org_member

router = APIRouter(prefix="/favorites", tags=["favorites"])

ALLOWED_TARGET_TYPES = frozenset({"artist", "venue"})


class FavoriteIn(BaseModel):
    target_type: str
    target_id: str = Field(min_length=1, max_length=36)
    organization_id: str | None = None

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in ALLOWED_TARGET_TYPES:
            raise ValueError("target_type: artist|venue")
        return normalized


def _resolve_org_id(
    db: Session,
    user: User,
    organization_id: str | None,
    x_booker_org: str | None,
) -> str:
    org_id = (organization_id or x_booker_org or user.active_organization_id or "").strip()
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужна организация")
    require_org_member(db, user, org_id)
    return org_id


def _ensure_target_exists(db: Session, target_type: str, target_id: str) -> tuple[str | None, str | None]:
    if target_type == "artist":
        row = db.get(Artist, target_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Артист не найден")
        return row.name, row.city
    row = db.get(Venue, target_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Площадка не найдена")
    return row.name, row.city


def _out(row: Favorite, *, name: str | None = None, city: str | None = None) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "organization_id": row.organization_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "name": name,
        "city": city,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _enrich(db: Session, row: Favorite) -> dict:
    name: str | None = None
    city: str | None = None
    if row.target_type == "artist":
        target = db.get(Artist, row.target_id)
        if target:
            name, city = target.name, target.city
    elif row.target_type == "venue":
        target = db.get(Venue, row.target_id)
        if target:
            name, city = target.name, target.city
    return _out(row, name=name, city=city)


@router.get("")
def list_favorites(
    organization_id: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _resolve_org_id(db, user, organization_id, x_booker_org)
    q = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.organization_id == org_id,
    )
    if target_type:
        normalized = target_type.strip().lower()
        if normalized not in ALLOWED_TARGET_TYPES:
            raise HTTPException(400, "target_type: artist|venue")
        q = q.filter(Favorite.target_type == normalized)
    if target_id:
        q = q.filter(Favorite.target_id == target_id.strip())
    rows = q.order_by(Favorite.created_at.desc()).all()
    return {"items": [_enrich(db, row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def add_favorite(
    body: FavoriteIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _resolve_org_id(db, user, body.organization_id, x_booker_org)
    name, city = _ensure_target_exists(db, body.target_type, body.target_id)
    existing = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.id,
            Favorite.organization_id == org_id,
            Favorite.target_type == body.target_type,
            Favorite.target_id == body.target_id,
        )
        .one_or_none()
    )
    if existing:
        return _out(existing, name=name, city=city)

    row = Favorite(
        user_id=user.id,
        organization_id=org_id,
        target_type=body.target_type,
        target_id=body.target_id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Favorite)
            .filter(
                Favorite.user_id == user.id,
                Favorite.organization_id == org_id,
                Favorite.target_type == body.target_type,
                Favorite.target_id == body.target_id,
            )
            .one_or_none()
        )
        if existing:
            return _out(existing, name=name, city=city)
        raise
    db.refresh(row)
    return _out(row, name=name, city=city)


@router.delete("/target/{target_type}/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite_by_target(
    target_type: str,
    target_id: str,
    organization_id: str | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    normalized = (target_type or "").strip().lower()
    if normalized not in ALLOWED_TARGET_TYPES:
        raise HTTPException(400, "target_type: artist|venue")
    org_id = _resolve_org_id(db, user, organization_id, x_booker_org)
    row = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.id,
            Favorite.organization_id == org_id,
            Favorite.target_type == normalized,
            Favorite.target_id == target_id,
        )
        .one_or_none()
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Избранное не найдено")
    db.delete(row)
    db.commit()
    return None


@router.delete("/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    favorite_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Favorite, favorite_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Избранное не найдено")
    # membership check keeps org-scoped authz consistent
    if not membership(db, user.id, row.organization_id) and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к организации")
    db.delete(row)
    db.commit()
    return None
