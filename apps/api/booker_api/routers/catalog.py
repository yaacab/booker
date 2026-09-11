import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from booker_api.calendar import MSK, calendar_day_bounds, open_slots_unmasked, overlapping_slots
from booker_api.composition import seed_categories
from booker_api.db import get_db
from booker_api.ical_import import calendar_targets, import_ical_source
from booker_api.demo_calendar import ensure_demo_day
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    CatalogCategory,
    Offer,
    Organization,
    Request,
    User,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from booker_api.schemas import (
    ArtistIn,
    IcalImportIn,
    SlotIn,
    TariffIn,
    VacationClearIn,
    VacationIn,
    VenueIn,
)
from booker_api.security import (
    audit,
    authenticate_token,
    aware,
    bearer,
    current_user,
    membership,
    now,
    require_org_member,
    require_org_writer,
)
from booker_api.vacation import clear_vacation, set_vacation, vacation_status
from booker_api.venue_catalog import public_disclosure

router = APIRouter(tags=["catalog"])

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



def _catalog_iso(dt: datetime | None) -> str | None:
    """Serialize slot times with an explicit MSK offset.

    SQLite often returns naive datetimes; without an offset, Next.js SSR on UTC
    hosts and browsers in Europe/Moscow parse them differently and the catalog
    page fails hydration (React #418).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MSK).isoformat()
    return dt.astimezone(MSK).isoformat()


def _hall_item(hall: VenueHall) -> dict:
    return {"id": hall.id, "name": hall.name, "capacity": hall.capacity}


def _slot_item(slot: AvailabilitySlot, *, hall: str | None = None) -> dict:
    uid = getattr(slot, "external_uid", None) or None
    busy_source = None
    if uid:
        if uid.startswith("ical:"):
            busy_source = "ical"
        elif uid.startswith("vacation:"):
            busy_source = "vacation"
    item = {
        "id": slot.id,
        "starts_at": _catalog_iso(slot.starts_at),
        "ends_at": _catalog_iso(slot.ends_at),
        "status": slot.status,
        "buffer_before_min": getattr(slot, "buffer_before_min", 0) or 0,
        "buffer_after_min": getattr(slot, "buffer_after_min", 0) or 0,
    }
    if busy_source:
        item["busy_source"] = busy_source
    if hall:
        item["hall"] = hall
    return item


def _halls_for_venue(db: Session, venue_id: str) -> list[VenueHall]:
    return db.query(VenueHall).filter(VenueHall.venue_id == venue_id).order_by(VenueHall.name).all()


def _public_venue_photos(db: Session, venue_id: str) -> list[dict]:
    rows = (
        db.query(VenuePhoto)
        .filter(
            VenuePhoto.venue_id == venue_id,
            VenuePhoto.photo_rights_status.in_(("licensed", "official_permission")),
        )
        .order_by(VenuePhoto.sort_order, VenuePhoto.id)
        .all()
    )
    return [
        {
            "url": row.photo_url,
            "source_url": row.photo_source_url,
            "rights_status": row.photo_rights_status,
        }
        for row in rows
    ]


def _research_venue_photos(db: Session, venue_id: str) -> list[dict]:
    rows = (
        db.query(VenuePhoto)
        .filter(
            VenuePhoto.venue_id == venue_id,
            VenuePhoto.photo_rights_status.in_(
                ("licensed", "official_permission", "unknown")
            ),
        )
        .order_by(VenuePhoto.sort_order, VenuePhoto.id)
        .all()
    )
    return [
        {
            "url": row.photo_url,
            "source_url": row.photo_source_url,
            "rights_status": row.photo_rights_status,
        }
        for row in rows
    ]


def _venue_in_catalog(db: Session, venue: Venue) -> bool:
    if venue.moderation_status != "published":
        return False
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
    try:
        user, _ = authenticate_token(db, creds.credentials)
        return user
    except HTTPException:
        return None


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
    require_org_writer(db, user, body.organization_id)
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
    require_org_writer(db, user, body.organization_id)
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
    require_org_writer(db, user, artist.organization_id)
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
    require_org_writer(db, user, venue.organization_id)
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
        require_org_writer(db, user, artist.organization_id)
    elif body.resource_type == "hall":
        hall = db.get(VenueHall, body.resource_id)
        if not hall:
            raise HTTPException(404, "Зал не найден")
        venue = db.get(Venue, hall.venue_id)
        require_org_writer(db, user, venue.organization_id)
    else:
        raise HTTPException(400, "resource_type: artist|hall")
    before = max(0, getattr(body, "buffer_before_min", 0) or 0)
    after = max(0, getattr(body, "buffer_after_min", 0) or 0)
    # Local open/held/confirmed conflict; busy is an overlay and may coexist.
    if overlapping_slots(
        db,
        body.resource_type,
        body.resource_id,
        body.starts_at,
        body.ends_at,
        statuses=("open", "held", "confirmed"),
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


@router.get("/organizations/{org_id}/vacation")
def get_vacation(
    org_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    require_org_member(db, user, org_id)
    if org.kind not in {"artist", "venue"}:
        return {"items": []}
    return vacation_status(db, org_id, org.kind)


@router.post("/calendar/vacation")
def post_vacation(
    body: VacationIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_writer(db, user, body.organization_id)
    try:
        return set_vacation(
            db,
            org_id=body.organization_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/calendar/vacation")
def delete_vacation(
    body: VacationClearIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_org_writer(db, user, body.organization_id)
    try:
        return clear_vacation(
            db,
            org_id=body.organization_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _parse_rider(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _rider_formats(rider: dict) -> list[str]:
    values: list[str] = []
    fmt = rider.get("format")
    if isinstance(fmt, str) and fmt.strip():
        values.append(fmt.strip().lower())
    formats = rider.get("formats")
    if isinstance(formats, list):
        values.extend(str(x).strip().lower() for x in formats if str(x).strip())
    elif isinstance(formats, str) and formats.strip():
        values.extend(part.strip().lower() for part in formats.split(",") if part.strip())
    return values


def _rider_travel_ok(rider: dict) -> bool | None:
    """True/False if rider declares travel; None = unknown (does not match travel=1 filter)."""
    for key in ("travel", "travel_ok", "выезд"):
        if key not in rider:
            continue
        val = rider[key]
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            low = val.strip().lower()
            if low in {"1", "true", "yes", "да", "ok"}:
                return True
            if low in {"0", "false", "no", "нет"}:
                return False
    return None


def _format_matches(rider: dict, needle: str) -> bool:
    needle_l = needle.strip().lower()
    if not needle_l:
        return True
    return any(needle_l in fmt for fmt in _rider_formats(rider))


def _min_tariff(tariffs: list) -> int | None:
    amounts = [int(t.honorarium_rub) for t in tariffs if getattr(t, "honorarium_rub", None) is not None]
    return min(amounts) if amounts else None


@router.get("/catalog/search")
def search_catalog(
    city: str = Query("Москва"),
    category: str | None = None,
    date: datetime | None = None,
    exclude: str | None = Query(None, description="Comma-separated artist/venue ids to hide"),
    format: str | None = Query(None, description="Substring match against artist rider format(s)"),
    travel: bool | None = Query(None, description="Require travel_ok in artist rider when true"),
    budget_max: int | None = Query(None, ge=0, description="Max honorarium (min tariff)"),
    guests: int | None = Query(None, ge=1, description="Minimum hall capacity"),
    seating: str | None = Query(None, description="Optional seating hint; filters halls/venues mentioning it"),
    kind: str | None = Query(None, description="artist | venue — narrow dual search"),
    district: str | None = Query(None, max_length=128),
    metro: str | None = Query(None, max_length=128),
    db: Session = Depends(get_db),
):
    """В выдаче только профили с календарём. Занятые слоты не считаются свободными."""
    ensure_demo_day(db, date or now())
    excluded = {item.strip() for item in (exclude or "").split(",") if item.strip()}
    kind_l = (kind or "").strip().lower() or None
    include_artists = kind_l != "venue" and (not category or category != "venue")
    include_venues = kind_l != "artist" and (not category or category == "venue")
    # Dual search: category=venue without kind still venues-only via include_artists false.
    if category == "venue":
        include_artists = False
        include_venues = True
    elif category and kind_l != "venue":
        include_venues = kind_l == "venue"

    horizon_end = now() + timedelta(days=30)
    results = []
    if include_artists:
        q = db.query(Artist).filter(Artist.city == city)
        if category and category != "venue":
            q = q.filter(Artist.category == category)
        for artist in q.all():
            if artist.id in excluded:
                continue
            rider = _parse_rider(artist.rider_json)
            if format and not _format_matches(rider, format):
                continue
            if travel is True and _rider_travel_ok(rider) is not True:
                continue
            if travel is False and _rider_travel_ok(rider) is True:
                continue
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
            open_future = open_slots_unmasked(
                slots, horizon_start=now(), horizon_end=horizon_end
            )
            if date:
                day_start, day_end = calendar_day_bounds(date)
                free = open_slots_unmasked(slots, day_start=day_start, day_end=day_end)
                if not free:
                    continue
            elif not open_future:
                continue
            tariffs = db.query(ArtistTariff).filter(ArtistTariff.artist_id == artist.id).all()
            if budget_max is not None:
                floor = _min_tariff(tariffs)
                if floor is None or floor > budget_max:
                    continue
            pool = free if date else open_future
            nxt = min(pool, key=lambda s: aware(s.starts_at)) if pool else None
            results.append(
                {
                    "id": artist.id,
                    "name": artist.name,
                    "media_url": artist.media_url,
                    "city": artist.city,
                    "category": artist.category,
                    "verified": artist.verified,
                    "has_calendar": True,
                    "open_slots": len(pool),
                    "next_open_at": _catalog_iso(nxt.starts_at) if nxt else None,
                    "search_date": aware(date).date().isoformat() if date else None,
                    "travel_ok": _rider_travel_ok(rider),
                    "formats": _rider_formats(rider),
                    "tariffs": [
                        {"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs
                    ],
                }
            )

    venue_results = []
    if include_venues:
        seating_l = (seating or "").strip().lower() or None
        for venue in db.query(Venue).filter(Venue.city == city).all():
            if venue.moderation_status != "published":
                continue
            if district and district.strip().casefold() not in (venue.district or "").casefold():
                continue
            if metro and metro.strip().casefold() not in (venue.metro or "").casefold():
                continue
            if venue.id in excluded:
                continue
            halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
            if guests is not None:
                matching = [h for h in halls if (h.capacity or 0) >= guests]
            else:
                matching = list(halls)
            if seating_l:
                blob = " ".join(
                    [
                        (getattr(venue, "description", "") or ""),
                        (getattr(venue, "name", "") or ""),
                        *[h.name for h in matching],
                    ]
                ).lower()
                if seating_l not in blob:
                    # Soft filter: keep venue only if hint appears; unknown seating does not invent match.
                    continue
            if guests is not None and not matching:
                continue
            hall_ids = {h.id for h in matching} if guests is not None else {h.id for h in halls}
            hall_slots = []
            for hall in halls:
                if hall.id not in hall_ids:
                    continue
                hall_slots.extend(
                    db.query(AvailabilitySlot)
                    .filter(
                        AvailabilitySlot.resource_type == "hall",
                        AvailabilitySlot.resource_id == hall.id,
                    )
                    .all()
                )
            if not hall_slots:
                continue
            open_future = open_slots_unmasked(
                hall_slots, horizon_start=now(), horizon_end=now() + timedelta(days=30)
            )
            pool = open_future
            if date:
                day_start, day_end = calendar_day_bounds(date)
                pool = open_slots_unmasked(hall_slots, day_start=day_start, day_end=day_end)
                if not pool:
                    continue
            elif not open_future:
                continue
            nxt = min(pool, key=lambda s: aware(s.starts_at))
            tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all()
            photos = _public_venue_photos(db, venue.id)
            if budget_max is not None and kind_l == "venue":
                floor = _min_tariff(tariffs)
                if floor is not None and floor > budget_max:
                    continue
            venue_results.append(
                {
                    "id": venue.id,
                    "name": venue.name,
                    "city": venue.city,
                    "category": "venue",
                    "verified": venue.verified,
                    "address": getattr(venue, "address", "") or "",
                    "district": getattr(venue, "district", "") or "",
                    "metro": getattr(venue, "metro", "") or "",
                    "availability_mode": getattr(venue, "availability_mode", "owner") or "owner",
                    "listing_origin": getattr(venue, "listing_origin", "owner") or "owner",
                    "source_type": venue.source_type,
                    "partnership_status": venue.partnership_status,
                    "public_disclosure": public_disclosure(venue),
                    "capacity": venue.capacity,
                    "matching_halls": [_hall_item(h) for h in matching],
                    "open_slots": len(pool),
                    "next_open_at": _catalog_iso(nxt.starts_at),
                    "tariffs": [{"honorarium_rub": t.honorarium_rub} for t in tariffs],
                    "cover_photo": photos[0] if photos else None,
                }
            )
    return {"items": results, "venues": venue_results}


@router.get("/catalog/demo/venues")
def list_investor_demo_venues(
    city: str = Query("Москва"),
    limit: int = Query(300, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Research cards for the clearly labelled private investor demo.

    This endpoint is intentionally separate from /catalog/search: imported
    venues have no invented availability and remain outside the live catalog.
    """
    rows = (
        db.query(Venue)
        .filter(Venue.city == city, Venue.source_type == "automated_import")
        .all()
    )
    items = []
    for venue in rows:
        try:
            details = json.loads(venue.details_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        if details.get("research_status") != "investor_demo_verified_listing":
            continue
        tariffs = (
            db.query(VenueTariff)
            .filter(VenueTariff.venue_id == venue.id)
            .order_by(VenueTariff.honorarium_rub)
            .all()
        )
        photos = _research_venue_photos(db, venue.id)
        if not tariffs or not photos:
            continue
        items.append(
            {
                "id": venue.id,
                "rank": details.get("rank") or 9999,
                "name": venue.name,
                "city": venue.city,
                "address": venue.address or "",
                "metro": venue.metro or "",
                "description": venue.description or "",
                "capacity": venue.capacity,
                "area_sqm": details.get("area_sqm"),
                "venue_type": venue.venue_type or "event_space",
                "performance_evidence": details.get("performance_evidence") or [],
                "has_stage": details.get("has_stage") is True,
                "has_sound": details.get("has_sound") is True,
                "has_light": details.get("has_light") is True,
                "tariff_from_rub": min(t.honorarium_rub for t in tariffs),
                "tariff_unit": details.get("tariff_unit") or "hour",
                "source_url": venue.source_url or "",
                "source_attribution": venue.source_attribution or "",
                "cover_photo": photos[0],
                "photos": photos,
                "photo_notice": "Внешние фото из карточки источника; права для публичной публикации не заявлены.",
                "availability_note": "Свободные даты и итоговую смету подтверждает площадка.",
            }
        )
    items.sort(key=lambda item: (item["rank"], item["name"]))
    return {
        "mode": "investor_demo_research",
        "count": min(len(items), limit),
        "items": items[:limit],
    }


@router.get("/venues/{venue_id}")
def get_venue(venue_id: str, db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    if venue.moderation_status != "published":
        raise HTTPException(404, "Площадка не найдена")
    halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
    tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all()
    photos = _public_venue_photos(db, venue.id)
    slots = []
    for hall in halls:
        for s in (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id == hall.id)
            .order_by(AvailabilitySlot.starts_at)
            .all()
        ):
            slots.append(_slot_item(s, hall=hall.name))
    return {
        "id": venue.id,
        "organization_id": venue.organization_id,
        "name": venue.name,
        "city": venue.city,
        "capacity": venue.capacity,
        "verified": venue.verified,
        "address": getattr(venue, "address", "") or "",
        "district": getattr(venue, "district", "") or "",
        "metro": getattr(venue, "metro", "") or "",
        "description": getattr(venue, "description", "") or "",
        "source_url": getattr(venue, "source_url", "") or "",
        "source_attribution": getattr(venue, "source_attribution", "") or "",
        "listing_origin": getattr(venue, "listing_origin", "owner") or "owner",
        "availability_mode": getattr(venue, "availability_mode", "owner") or "owner",
        "source_type": venue.source_type,
        "partnership_status": venue.partnership_status,
        "public_disclosure": public_disclosure(venue),
        "data_freshness_status": venue.data_freshness_status,
        "official_website": venue.official_website,
        "details": json.loads(venue.details_json or "{}"),
        "facts": {
            "note": (
                "Календарь ориентировочный: слоты синтетические, доступность не подтверждена владельцем."
                if (getattr(venue, "availability_mode", "owner") or "owner") == "synthetic"
                else "Звёзды повесим после десяти закрытых вечеров. Пока — факты, не магия."
            )
        },
        "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
        "photos": photos,
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
        "slots": [_slot_item(s) for s in slots],
    }
