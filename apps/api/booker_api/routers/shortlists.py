"""Share selected public profiles without granting account or event access."""
import secrets
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.collaboration import (
    active_share,
    digest,
    guest_for,
    limit,
    public_text,
    shared_payload,
    visible_item,
)
from booker_api.composition import ROLE_LABEL
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_commands import remember_command, replay_command
from booker_api.models import (
    Artist,
    Event,
    Favorite,
    Organization,
    SharedShortlist,
    SharedShortlistItem,
    ShortlistFeedback,
    ShortlistGuest,
    User,
    Venue,
    VenueHall,
)
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import (
    audit,
    aware,
    current_user,
    membership,
    now,
    require_org_member,
    require_org_writer,
)
from booker_api.venue_catalog import is_publicly_listed

router = APIRouter(tags=["shortlists"])
ALLOWED_TYPES = frozenset({"artist", "venue"})


class ShortlistCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str | None = None
    event_id: UUID | None = None
    target_type: Literal["artist", "venue"]
    title: str = Field(default="Подборка", min_length=1, max_length=120)
    favorite_ids: list[str] = Field(min_length=2, max_length=4)
    ttl_days: int = Field(default=14, ge=1, le=90)
    collaborative: bool = False

    @field_validator("title")
    @classmethod
    def title_text(cls, value):
        return public_text(value) or "Подборка"


class GuestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=60)
    guest_secret: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("display_name")
    @classmethod
    def name_text(cls, value):
        value = public_text(value)
        if not value:
            raise ValueError("Укажите имя для обсуждения")
        return value


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reaction: Literal["vote", "favorite", "reject"] | None = None
    comment: str = Field(default="", max_length=1000)
    expected_revision: int = Field(ge=0, strict=True)

    @field_validator("comment")
    @classmethod
    def comment_text(cls, value):
        return public_text(value)


def _org_id(db, user, organization_id, x_booker_org):
    org_id = (organization_id or x_booker_org or user.active_organization_id or "").strip()
    if not org_id:
        raise HTTPException(400, "Нужна организация")
    require_org_member(db, user, org_id)
    return org_id


def _snapshot(db, kind, target_id):
    if kind == "artist":
        row = db.get(Artist, target_id)
        if not row:
            raise HTTPException(404, "Профиль недоступен")
        return row.name, row.city or "", ROLE_LABEL.get(row.category, "Исполнитель")
    row = db.get(Venue, target_id)
    if not row or not is_publicly_listed(db, row):
        raise HTTPException(404, "Профиль недоступен")
    halls = db.query(VenueHall).filter_by(venue_id=row.id).all()
    return row.name, row.city or "", f"Вместимость одного зала до {max([h.capacity for h in halls], default=row.capacity)}"


def _out(db, row, *, can_manage=True, include_token=False):
    data = {**shared_payload(db, row), "id": row.id, "organization_id": row.organization_id, "event_id": row.event_id,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None, "created_at": row.created_at.isoformat(),
        "active": row.revoked_at is None and aware(row.expires_at) > now(), "can_manage": can_manage}
    if can_manage:
        data["share_path"] = f"/s/{row.token}"
    if include_token:
        data["token"] = row.token
    return data


def _managed(db, user, shortlist_id, *, writer=False):
    row = db.get(SharedShortlist, str(shortlist_id))
    if not row or (not user.is_platform_admin and not membership(db, user.id, row.organization_id)):
        raise HTTPException(404, "Подборка не найдена")
    (require_org_writer if writer else require_org_member)(db, user, row.organization_id)
    return row


@router.post("/shortlists", status_code=201)
def create_shortlist(body: ShortlistCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=160)):
    org_id = _org_id(db, user, body.organization_id, x_booker_org)
    require_org_writer(db, user, org_id)
    messaging_limiter.check(f"shortlist-create:{user.id}")
    if body.collaborative and not settings.collaborative_events:
        raise HTTPException(503, "Совместные обсуждения временно отключены")
    if body.event_id:
        event = db.get(Event, str(body.event_id))
        if not event or event.organization_id != org_id:
            raise HTTPException(404, "Событие не найдено в этой организации")
    db.execute(update(Organization).where(Organization.id == org_id).values(name=Organization.name))
    scope = f"shortlist:{org_id}:{user.id}"
    command = body.model_dump(mode="json")
    previous = replay_command(db, scope, idempotency_key, command)
    if previous:
        return {**_out(db, _managed(db, user, previous['id'], writer=True), include_token=True), "reused": True}
    if db.query(SharedShortlist).filter(SharedShortlist.organization_id == org_id, SharedShortlist.revoked_at.is_(None), SharedShortlist.expires_at > now()).count() >= 20:
        raise HTTPException(409, "У организации уже 20 активных подборок. Отзовите ненужные ссылки")
    if len(set(body.favorite_ids)) != len(body.favorite_ids):
        raise HTTPException(422, "Выберите разных кандидатов")
    favs = db.query(Favorite).filter(Favorite.id.in_(body.favorite_ids), Favorite.user_id == user.id, Favorite.organization_id == org_id, Favorite.target_type == body.target_type).all()
    if len(favs) != len(body.favorite_ids):
        raise HTTPException(400, "Некоторые кандидаты не найдены в вашем избранном")
    row = SharedShortlist(owner_user_id=user.id, organization_id=org_id, event_id=str(body.event_id) if body.event_id else None,
        target_type=body.target_type, title=body.title, token=secrets.token_urlsafe(24), expires_at=now()+timedelta(days=body.ttl_days), collaborative=body.collaborative)
    db.add(row); db.flush()
    for index, favorite_id in enumerate(body.favorite_ids):
        fav = next(f for f in favs if f.id == favorite_id)
        name, city, summary = _snapshot(db, fav.target_type, fav.target_id)
        db.add(SharedShortlistItem(shortlist_id=row.id, target_id=fav.target_id, name=name, city=city, summary=summary, sort_order=index))
    audit(db, actor_user_id=user.id, action="shortlist.created", entity_type="shared_shortlist", entity_id=row.id,
        payload={"target_type": body.target_type, "items": len(favs), "collaborative": row.collaborative, "with_event": bool(row.event_id)})
    remember_command(db, scope, idempotency_key, command, {"id": row.id})
    db.commit(); db.refresh(row)
    return _out(db, row, include_token=True)


@router.get("/shortlists")
def list_shortlists(organization_id: str | None = None, event_id: UUID | None = None, user: User = Depends(current_user), db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org")):
    org_id = _org_id(db, user, organization_id, x_booker_org)
    member = require_org_member(db, user, org_id)
    analytics_limiter.check(f"shortlist-list:{user.id}")
    query = db.query(SharedShortlist).filter_by(organization_id=org_id)
    if event_id:
        event = db.get(Event, str(event_id))
        if not event or event.organization_id != org_id:
            raise HTTPException(404, "Событие не найдено в этой организации")
        query = query.filter_by(event_id=str(event_id))
    can_manage = member.role in {"owner", "admin", "manager"}
    rows = query.order_by(SharedShortlist.revoked_at.is_(None).desc(), SharedShortlist.expires_at.desc()).limit(100).all()
    audit(db, actor_user_id=user.id, action="shortlist.results_viewed", entity_type="organization", entity_id=org_id, payload={"count": len(rows)})
    result = {"items": [_out(db, row, can_manage=can_manage) for row in rows], "can_manage": can_manage, "collaboration_enabled": settings.collaborative_events}
    db.commit()
    return result


@router.post("/shortlists/{shortlist_id}/revoke")
def revoke_shortlist(shortlist_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _managed(db, user, shortlist_id, writer=True)
    messaging_limiter.check(f"shortlist-revoke:{user.id}")
    db.execute(update(SharedShortlist).where(SharedShortlist.id == row.id).values(title=SharedShortlist.title)); db.refresh(row)
    if row.revoked_at is None:
        row.revoked_at = now()
        audit(db, actor_user_id=user.id, action="shortlist.revoked", entity_type="shared_shortlist", entity_id=row.id, payload={})
    db.commit(); db.refresh(row)
    return _out(db, row, include_token=True)


def _private_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'


@router.get("/shared/{token}")
def public_shared_shortlist(token: str, request: Request, response: Response, db: Session = Depends(get_db),
    guest_secret: str | None = Header(default=None, alias="X-Shortlist-Guest")):
    limit(request); _private_headers(response)
    row = active_share(db, token)
    guest = guest_for(db, row, guest_secret)
    result = shared_payload(db, row, guest)
    audit(db, actor_user_id=None, action="shortlist.viewed", entity_type="shared_shortlist", entity_id=row.id, payload={"collaborative": row.collaborative})
    db.commit()
    return result


@router.post("/shared/{token}/guests")
def join_shortlist(token: str, body: GuestIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(request, write=True); _private_headers(response)
    row = active_share(db, token, lock=True, write=True)
    guest = guest_for(db, row, body.guest_secret)
    if guest and guest.display_name != body.display_name:
        raise HTTPException(409, "Это устройство уже участвует под другим именем")
    if not guest:
        if db.query(ShortlistGuest).filter_by(shortlist_id=row.id).count() >= 50:
            raise HTTPException(409, "В подборке уже 50 гостевых участников")
        guest = ShortlistGuest(shortlist_id=row.id, secret_hash=digest(body.guest_secret), display_name=body.display_name)
        db.add(guest); db.flush()
        audit(db, actor_user_id=None, action="shortlist.guest_joined", entity_type="shared_shortlist", entity_id=row.id, payload={})
    result = shared_payload(db, row, guest)
    db.commit()
    return result


@router.put("/shared/{token}/items/{target_id}/feedback")
def update_feedback(token: str, target_id: UUID, body: FeedbackIn, request: Request, response: Response, db: Session = Depends(get_db),
    guest_secret: str | None = Header(default=None, alias="X-Shortlist-Guest")):
    limit(request, write=True); _private_headers(response)
    row = active_share(db, token, lock=True, write=True)
    guest = guest_for(db, row, guest_secret, required=True)
    item = next((i for i in row.items if i.target_id == str(target_id)), None)
    if not item or not visible_item(db, row.target_type, item):
        raise HTTPException(404, "Кандидат недоступен в этой подборке")
    feedback = db.query(ShortlistFeedback).filter_by(guest_id=guest.id, item_id=item.id).one_or_none()
    revision = feedback.revision if feedback else 0
    same = (feedback.reaction if feedback else None) == body.reaction and (feedback.comment if feedback else "") == body.comment
    if not same:
        if revision != body.expected_revision:
            raise HTTPException(409, "Ваше мнение уже изменено в другой вкладке. Обновите обсуждение")
        if not feedback:
            feedback = ShortlistFeedback(guest_id=guest.id, item_id=item.id)
            db.add(feedback)
        feedback.reaction, feedback.comment = body.reaction, body.comment
        feedback.revision, feedback.updated_at = revision+1, now()
        db.flush()
        audit(db, actor_user_id=None, action="shortlist.feedback_updated", entity_type="shared_shortlist", entity_id=row.id,
            payload={"reaction": body.reaction, "has_comment": bool(body.comment), "revision": feedback.revision})
    result = shared_payload(db, row, guest)
    db.commit()
    return result
