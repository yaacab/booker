import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from booker_api.calendar import calendar_day_bounds, overlapping_slots, ranges_overlap
from booker_api.db import get_db
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.schemas import ArtistIn, SlotIn, TariffIn, VenueIn
from booker_api.security import audit, aware, current_user, now, require_org_member

router = APIRouter(tags=["catalog"])


@router.post("/artists")
def create_artist(body: ArtistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_org_member(db, user, body.organization_id)
    artist = Artist(
        organization_id=body.organization_id,
        name=body.name,
        city=body.city,
        category=body.category,
        media_url=body.media_url,
        rider_json=body.rider_json,
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    return {"id": artist.id, "name": artist.name}


@router.post("/venues")
def create_venue(body: VenueIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_org_member(db, user, body.organization_id)
    venue = Venue(
        organization_id=body.organization_id,
        name=body.name,
        city=body.city,
        capacity=body.capacity,
    )
    db.add(venue)
    db.flush()
    hall = VenueHall(venue_id=venue.id, name="Основной зал", capacity=body.capacity)
    db.add(hall)
    db.commit()
    db.refresh(venue)
    db.refresh(hall)
    return {"id": venue.id, "hall_id": hall.id}


@router.post("/artists/{artist_id}/tariffs")
def add_tariff(
    artist_id: str,
    body: TariffIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    require_org_member(db, user, artist.organization_id)
    row = ArtistTariff(
        artist_id=artist_id,
        title=body.title,
        honorarium_rub=body.honorarium_rub,
        hours=body.hours,
    )
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.post("/venues/{venue_id}/tariffs")
def add_venue_tariff(
    venue_id: str,
    body: TariffIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    require_org_member(db, user, venue.organization_id)
    row = VenueTariff(venue_id=venue_id, title=body.title, honorarium_rub=body.honorarium_rub)
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.post("/slots")
def create_slot(body: SlotIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.resource_type == "artist":
        artist = db.get(Artist, body.resource_id)
        if not artist:
            raise HTTPException(404, "Артист не найден")
        require_org_member(db, user, artist.organization_id)
    elif body.resource_type == "hall":
        hall = db.get(VenueHall, body.resource_id)
        if not hall:
            raise HTTPException(404, "Зал не найден")
        venue = db.get(Venue, hall.venue_id)
        require_org_member(db, user, venue.organization_id)
    else:
        raise HTTPException(400, "resource_type: artist|hall")
    if overlapping_slots(
        db,
        body.resource_type,
        body.resource_id,
        body.starts_at,
        body.ends_at,
        statuses=("open", "held", "confirmed"),
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пересечение слотов")
    slot = AvailabilitySlot(
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        status="open",
    )
    db.add(slot)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="slot.created",
        entity_type="slot",
        entity_id=slot.id,
    )
    db.commit()
    db.refresh(slot)
    return {"id": slot.id, "status": slot.status}


@router.get("/catalog/search")
def search_catalog(
    city: str = Query("Москва"),
    category: str | None = None,
    date: datetime | None = None,
    db: Session = Depends(get_db),
):
    """В выдаче только профили с календарём. Занятые слоты не считаются свободными."""
    q = db.query(Artist).filter(Artist.city == city)
    if category:
        q = q.filter(Artist.category == category)
    horizon_end = now() + timedelta(days=30)
    results = []
    for artist in q.all():
        slots = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "artist",
                AvailabilitySlot.resource_id == artist.id,
            )
            .all()
        )
        if not slots:
            continue
        open_future = [
            s
            for s in slots
            if s.status == "open" and aware(s.ends_at) >= now() and aware(s.starts_at) <= horizon_end
        ]
        if date:
            day_start, day_end = calendar_day_bounds(date)
            free = [
                s
                for s in slots
                if s.status == "open" and ranges_overlap(s.starts_at, s.ends_at, day_start, day_end)
            ]
            if not free:
                continue
        elif not open_future:
            continue
        tariffs = db.query(ArtistTariff).filter(ArtistTariff.artist_id == artist.id).all()
        pool = free if date else open_future
        nxt = min(pool, key=lambda s: aware(s.starts_at)) if pool else None
        results.append(
            {
                "id": artist.id,
                "name": artist.name,
                "city": artist.city,
                "category": artist.category,
                "verified": artist.verified,
                "has_calendar": True,
                "open_slots": len(pool),
                "next_open_at": nxt.starts_at.isoformat() if nxt else None,
                "search_date": aware(date).date().isoformat() if date else None,
                "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
            }
        )
    venue_results = []
    if not category or category == "venue":
        for venue in db.query(Venue).filter(Venue.city == city).all():
            halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
            hall_slots = []
            for hall in halls:
                hall_slots.extend(
                    db.query(AvailabilitySlot)
                    .filter(AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id == hall.id)
                    .all()
                )
            if not hall_slots:
                continue
            open_future = [
                s
                for s in hall_slots
                if s.status == "open" and aware(s.ends_at) >= now() and aware(s.starts_at) <= now() + timedelta(days=30)
            ]
            pool = open_future
            if date:
                day_start, day_end = calendar_day_bounds(date)
                pool = [
                    s
                    for s in hall_slots
                    if s.status == "open" and ranges_overlap(s.starts_at, s.ends_at, day_start, day_end)
                ]
                if not pool:
                    continue
            elif not open_future:
                continue
            nxt = min(pool, key=lambda s: aware(s.starts_at))
            tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all()
            venue_results.append(
                {
                    "id": venue.id,
                    "name": venue.name,
                    "city": venue.city,
                    "category": "venue",
                    "verified": venue.verified,
                    "open_slots": len(pool),
                    "next_open_at": nxt.starts_at.isoformat(),
                    "tariffs": [{"honorarium_rub": t.honorarium_rub} for t in tariffs],
                }
            )
    return {"items": results, "venues": venue_results}


@router.get("/venues/{venue_id}")
def get_venue(venue_id: str, db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
    tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all()
    slots = []
    for hall in halls:
        for s in (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id == hall.id)
            .order_by(AvailabilitySlot.starts_at)
            .all()
        ):
            slots.append(
                {
                    "id": s.id,
                    "hall": hall.name,
                    "starts_at": s.starts_at.isoformat(),
                    "ends_at": s.ends_at.isoformat(),
                    "status": s.status,
                }
            )
    return {
        "id": venue.id,
        "name": venue.name,
        "city": venue.city,
        "capacity": venue.capacity,
        "verified": venue.verified,
        "facts": {"note": "Звёзды повесим после десяти закрытых вечеров. Пока — факты, не магия."},
        "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
        "slots": slots,
    }


@router.get("/artists/{artist_id}")
def get_artist(artist_id: str, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    slots = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == "artist",
            AvailabilitySlot.resource_id == artist.id,
        )
        .order_by(AvailabilitySlot.starts_at)
        .all()
    )
    tariffs = db.query(ArtistTariff).filter(ArtistTariff.artist_id == artist.id).all()
    try:
        rider = json.loads(artist.rider_json or "{}")
        if not isinstance(rider, dict):
            rider = {}
    except (json.JSONDecodeError, TypeError):
        rider = {}
    return {
        "id": artist.id,
        "name": artist.name,
        "city": artist.city,
        "category": artist.category,
        "verified": artist.verified,
        "verified_status": artist.verified_status,
        "media_url": artist.media_url,
        "rider": rider,
        "facts": {
            "deals": 0,
            "response": "в пилоте обычно за пару часов",
            "note": "Рейтинг из восьми факторов подождёт. Сначала десять живых отзывов, потом цирк.",
        },
        "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
        "slots": [
            {
                "id": s.id,
                "starts_at": s.starts_at.isoformat(),
                "ends_at": s.ends_at.isoformat(),
                "status": s.status,
            }
            for s in slots
        ],
    }
