from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from booker_api.comparison import comparison_columns
from booker_api.compatibility import event_slot_ids
from booker_api.db import get_db
from booker_api.models import Artist, Event, Venue, VenueHall
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.security import audit, authenticate_token, aware, bearer, require_org_member
from booker_api.venue_catalog import is_publicly_listed

router = APIRouter(tags=["compare"])


@router.get("/compare")
def compare_candidates(request: Request, target_type: Literal["artist", "venue"], ids: str = Query(max_length=160),
    starts_at: datetime | None = None, ends_at: datetime | None = None,
    guest_count: int | None = Query(default=None, ge=1, le=100000), event_id: UUID | None = None,
    artist_id: UUID | None = None, venue_id: UUID | None = None, hall_id: UUID | None = None,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    raw = [i.strip() for i in ids.split(",") if i.strip()]
    try:
        chosen = [str(UUID(i)) for i in raw]
    except ValueError:
        raise HTTPException(422, "Откройте сравнение из профилей или избранного") from None
    if not 2 <= len(chosen) <= 4 or len(set(chosen)) != len(chosen):
        raise HTTPException(422, "Выберите от двух до четырёх разных профилей")
    user = authenticate_token(db, creds.credentials)[0] if creds else None
    own, event_city = set(), None
    if event_id:
        if not user:
            raise HTTPException(401, "Войдите, чтобы сравнить для своего события")
        event = db.get(Event, str(event_id))
        if not event:
            raise HTTPException(404, "Событие не найдено")
        require_org_member(db, user, event.organization_id)
        starts_at, ends_at, guest_count, event_city = event.event_date, event.ends_at, event.guest_count, event.city
        own = event_slot_ids(db, event.id)
    elif bool(starts_at) != bool(ends_at):
        raise HTTPException(422, "Укажите начало и окончание вместе")
    if starts_at and ends_at and aware(ends_at) <= aware(starts_at):
        raise HTTPException(422, "Окончание должно быть позже начала")
    analytics_limiter.check(f"compare:{user.id}" if user else client_key(request, "compare"))

    def venue(value):
        row = db.get(Venue, str(value)) if value else None
        if value and (not row or not is_publicly_listed(db, row)):
            raise HTTPException(404, "Один из профилей недоступен")
        return row

    profiles = [db.get(Artist, value) if target_type == "artist" else venue(value) for value in chosen]
    if any(p is None for p in profiles):
        raise HTTPException(404, "Один из профилей недоступен")
    artist = db.get(Artist, str(artist_id)) if artist_id else None
    if artist_id and not artist:
        raise HTTPException(404, "Один из профилей недоступен")
    reference = venue(venue_id)
    hall = db.get(VenueHall, str(hall_id)) if hall_id else None
    if hall_id and (not hall or not reference or hall.venue_id != reference.id):
        raise HTTPException(422, "Выберите зал указанной площадки")
    if reference and not hall:
        rooms = db.query(VenueHall).filter_by(venue_id=reference.id).all()
        hall = rooms[0] if len(rooms) == 1 else None
    result = comparison_columns(db, target_type, profiles, start=starts_at, end=ends_at, guests=guest_count,
        own_slots=own, reference_artist=artist, reference_venue=reference, reference_hall=hall, event_city=event_city)
    result["event_id"] = str(event_id) if event_id else None
    audit(db, actor_user_id=user.id if user else None, action="compare.opened", entity_type="compare", entity_id="selection",
          payload={"target_type": target_type, "count": len(chosen), "with_event": bool(event_id)})
    db.commit()
    return result
