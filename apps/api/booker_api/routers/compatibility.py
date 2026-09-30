import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.compatibility import HallFacts, assess_compatibility, event_slot_ids, hall_facts
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import (
    Artist,
    Event,
    HallTechnicalProfile,
    User,
    Venue,
    VenueHall,
)
from booker_api.rate_limit import analytics_limiter, client_key, upload_limiter
from booker_api.routers.catalog import _optional_user
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

router = APIRouter(tags=["compatibility"])


class HallFactsIn(HallFacts):
    expected_version: int = Field(strict=True, ge=0)


class CompatibilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artist_id: UUID
    venue_id: UUID
    hall_id: UUID | None = None
    event_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    guest_count: int | None = Field(default=None, strict=True, ge=1, le=100000)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.starts_at and self.ends_at and aware(self.ends_at) <= aware(self.starts_at):
            raise ValueError("Окончание должно быть позже начала")
        if not self.event_id and bool(self.starts_at) != bool(self.ends_at):
            raise ValueError("Укажите начало и окончание события")
        return self


def owned_hall(db, user, hall_id, writer=False):
    hall = db.get(VenueHall, hall_id)
    venue = db.get(Venue, hall.venue_id) if hall else None
    if not hall or not venue:
        raise HTTPException(404, "Зал не найден")
    (require_org_writer if writer else require_org_member)(db, user, venue.organization_id)
    return hall, venue


@router.get("/organizations/{org_id}/technical-halls")
def list_technical_halls(org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    member = require_org_member(db, user, org_id)
    rows = db.query(VenueHall, Venue).join(Venue, Venue.id == VenueHall.venue_id).filter(Venue.organization_id == org_id).order_by(Venue.name, VenueHall.name).all()
    return {"items": [{"id": h.id, "name": h.name, "venue_id": v.id, "venue_name": v.name} for h, v in rows],
            "can_manage": member.role in {"owner", "admin", "manager"}}


@router.get("/halls/{hall_id}/technical")
def get_technical(hall_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    hall, venue = owned_hall(db, user, hall_id)
    version, data = hall_facts(db, hall)
    return {"version": version, "data": data, "name": hall.name, "venue_name": venue.name}


@router.put("/halls/{hall_id}/technical")
def put_technical(hall_id: str, body: HallFactsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    hall, venue = owned_hall(db, user, hall_id, writer=True)
    upload_limiter.check(f"hall-technical:{user.id}")
    # Serialize all halls of the venue so its capacity aggregate cannot lose an update.
    db.execute(update(Venue).where(Venue.id == venue.id).values(name=Venue.name))
    db.refresh(hall)
    version, old = hall_facts(db, hall)
    data = body.model_dump(exclude={"expected_version"})
    if data == old and body.expected_version <= version:
        return {"version": version, "data": old, "idempotent": True}
    if body.expected_version != version:
        raise HTTPException(409, "Параметры зала уже изменены. Загрузите актуальную версию")
    row = db.get(HallTechnicalProfile, hall_id)
    if not row:
        row = HallTechnicalProfile(hall_id=hall_id, version=1)
        db.add(row)
    else:
        row.version += 1
    row.data_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    row.updated_at = now()
    hall.capacity = body.capacity
    venue.capacity = max(h.capacity for h in db.query(VenueHall).filter_by(venue_id=venue.id).all())
    audit(db, actor_user_id=user.id, action="hall.technical_updated", entity_type="hall", entity_id=hall.id,
          payload={"version": row.version, "changed_fields": [k for k in data if data[k] != old.get(k)]})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Параметры зала уже изменены. Обновите страницу") from None
    return {"version": row.version, "data": data}


@router.post("/compatibility")
def compatibility(body: CompatibilityIn, request: Request, user: User | None = Depends(_optional_user), db: Session = Depends(get_db)):
    if not settings.compatibility:
        raise HTTPException(503, "Проверка совместимости временно недоступна")
    analytics_limiter.check(client_key(request, "compatibility"))
    start, end, guests = body.starts_at, body.ends_at, body.guest_count
    own_slots = set()
    event_city = None
    if body.event_id:
        if not user:
            raise HTTPException(401, "Войдите для доступа к событию")
        event = db.get(Event, str(body.event_id))
        if not event:
            raise HTTPException(404, "Событие не найдено")
        require_org_member(db, user, event.organization_id)
        start, guests = event.event_date, event.guest_count
        event_city = event.city
        end = getattr(event, "ends_at", None) or end
        if end and aware(end) <= aware(start):
            raise HTTPException(422, "Окончание должно быть позже начала события")
        own_slots = event_slot_ids(db, event.id)
    artist = db.get(Artist, str(body.artist_id))
    venue = db.get(Venue, str(body.venue_id))
    if not artist or not venue:
        raise HTTPException(404, "Профиль не найден")
    can_manage_venue = bool(
        user
        and (
            user.is_platform_admin
            or membership(db, user.id, venue.organization_id)
        )
    )
    if not is_publicly_listed(db, venue) and not can_manage_venue:
        raise HTTPException(404, "Площадка не найдена")
    halls = db.query(VenueHall).filter_by(venue_id=venue.id).all()
    hall = next((h for h in halls if h.id == str(body.hall_id)), None) if body.hall_id else halls[0] if len(halls) == 1 else None
    if body.hall_id and not hall:
        raise HTTPException(404, "Зал не найден у выбранной площадки")
    result = assess_compatibility(db, artist=artist, venue=venue, hall=hall, starts_at=start, ends_at=end,
                                  guest_count=guests, own_slot_ids=own_slots, event_city=event_city)
    result["halls"] = [{"id": h.id, "name": h.name} for h in halls]
    audit(db, actor_user_id=user.id if user else None, action="compatibility.viewed", entity_type="artist", entity_id=artist.id,
          payload={"venue_id": venue.id, "hall_id": hall.id if hall else None, "status": result["status"], "event_id": str(body.event_id) if body.event_id else None})
    db.commit()
    return result
