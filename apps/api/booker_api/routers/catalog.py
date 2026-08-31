import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from booker_api.calendar import calendar_day_bounds, overlapping_slots, ranges_overlap
from booker_api.composition import seed_categories
from booker_api.db import get_db
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    CatalogCategory,
    Offer,
    Organization,
    Request,
    SessionToken,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)


def _supplier_deals_count(db: Session, org_id: str) -> int:
    return (
        db.query(Booking)
        .join(Offer, Booking.offer_id == Offer.id)
        .join(Request, Offer.request_id == Request.id)
        .filter(
            Request.supplier_org_id == org_id,
            Booking.status.in_(("Confirmed", "InProgress", "Completed")),
        )
        .count()
    )
from booker_api.ical_import import calendar_targets, import_ical_source
from booker_api.schemas import ArtistIn, IcalImportIn, SlotIn, TariffIn, VenueIn
from booker_api.security import (
    audit,
    aware,
    bearer,
    current_user,
    membership,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["catalog"])


def _hall_item(hall: VenueHall) -> dict:
    return {"id": hall.id, "name": hall.name, "capacity": hall.capacity}


def _halls_for_venue(db: Session, venue_id: str) -> list[VenueHall]:
    return db.query(VenueHall).filter(VenueHall.venue_id == venue_id).order_by(VenueHall.name).all()


def _venue_in_catalog(db: Session, venue: Venue) -> bool:
    halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
    hall_ids = [hall.id for hall in halls]
    if not hall_ids:
        return False
    return (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == "hall",
            AvailabilitySlot.resource_id.in_(hall_ids),
        )
        .first()
        is not None
    )


def _optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    row = db.get(SessionToken, creds.credentials)
    if not row:
        return None
    return db.get(User, row.user_id)


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    seed_categories(db)
    db.commit()
    rows = (
        db.query(CatalogCategory)
        .filter(CatalogCategory.published.is_(True))
        .order_by(CatalogCategory.sort_order, CatalogCategory.code)
        .all()
    )
    return {
        "items": [
            {"code": r.code, "title": r.title, "group_code": r.group_code}
            for r in rows
        ]
    }


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


@router.get("/venues/{venue_id}/halls")
def list_halls(
    venue_id: str,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    if not _venue_in_catalog(db, venue):
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
        member = membership(db, user.id, venue.organization_id)
        if not member and not user.is_platform_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к организации")
    halls = _halls_for_venue(db, venue.id)
    return {"items": [_hall_item(h) for h in halls]}


@router.post("/venues/{venue_id}/halls")
def create_hall(
    venue_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    require_org_writer(db, user, venue.organization_id)
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name обязателен")
    if "capacity" not in body or body.get("capacity") is None:
        raise HTTPException(400, "capacity обязателен")
    try:
        capacity = int(body["capacity"])
    except (TypeError, ValueError):
        raise HTTPException(400, "capacity должен быть числом")
    hall = VenueHall(venue_id=venue.id, name=name, capacity=capacity)
    db.add(hall)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="hall.created",
        entity_type="hall",
        entity_id=hall.id,
        payload={"venue_id": venue.id, "name": name},
    )
    db.commit()
    db.refresh(hall)
    return _hall_item(hall)


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
    before = max(0, getattr(body, "buffer_before_min", 0) or 0)
    after = max(0, getattr(body, "buffer_after_min", 0) or 0)
    if overlapping_slots(
        db,
        body.resource_type,
        body.resource_id,
        body.starts_at,
        body.ends_at,
        statuses=("open", "held", "confirmed", "busy"),
        buffer_before_min=before,
        buffer_after_min=after,
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пересечение слотов")
    slot = AvailabilitySlot(
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        status="open",
    )
    if hasattr(slot, "buffer_before_min") and getattr(body, "buffer_before_min", None) is not None:
        slot.buffer_before_min = before
    if hasattr(slot, "buffer_after_min") and getattr(body, "buffer_after_min", None) is not None:
        slot.buffer_after_min = after
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
    return {
        "id": slot.id,
        "status": slot.status,
        "buffer_before_min": getattr(slot, "buffer_before_min", 0) or 0,
        "buffer_after_min": getattr(slot, "buffer_after_min", 0) or 0,
    }


@router.get("/organizations/{org_id}/calendar-targets")
def list_calendar_targets(
    org_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    require_org_member(db, user, org_id)
    return {"items": calendar_targets(db, org_id, org.kind)}


@router.post("/calendar/ical/import")
async def import_ical_busy(
    body: IcalImportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_writer(db, user, body.organization_id)
    try:
        return await import_ical_source(
            db,
            org_id=body.organization_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            ical_url=body.ical_url,
            ical_body=body.ical_body,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось загрузить iCal") from exc


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
                    "buffer_before_min": getattr(s, "buffer_before_min", 0) or 0,
                    "buffer_after_min": getattr(s, "buffer_after_min", 0) or 0,
                }
            )
    return {
        "id": venue.id,
        "organization_id": venue.organization_id,
        "name": venue.name,
        "city": venue.city,
        "capacity": venue.capacity,
        "verified": venue.verified,
        "facts": {"note": "Звёзды повесим после десяти закрытых вечеров. Пока — факты, не магия."},
        "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
        "halls": [_hall_item(h) for h in halls],
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
            "deals": _supplier_deals_count(db, artist.organization_id),
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
                "buffer_before_min": getattr(s, "buffer_before_min", 0) or 0,
                "buffer_after_min": getattr(s, "buffer_after_min", 0) or 0,
            }
            for s in slots
        ],
    }
