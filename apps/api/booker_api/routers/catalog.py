import base64
import binascii
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi import Request as FastAPIRequest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from booker_api.calendar import MSK, calendar_day_bounds, open_slots_unmasked, overlapping_slots
from booker_api.composition import seed_categories
from booker_api.db import get_db
from booker_api.ical_import import calendar_targets, import_ical_source
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    CatalogCategory,
    Offer,
    Organization,
    Request,
    Service,
    User,
    Venue,
    VenueHall,
    VenuePhoto,
    VenueTariff,
)
from booker_api.publication_eligibility import (
    PUBLIC_MEDIA_RIGHTS,
    artist_publication_eligibility,
    batch_publication_eligibility,
    venue_publication_eligibility,
)
from booker_api.schemas import (
    ArtistIn,
    ArtistPublicationEvidenceIn,
    IcalImportIn,
    PublicationStateIn,
    SlotIn,
    TariffIn,
    VacationClearIn,
    VacationIn,
    VenueIn,
    VenuePhotoIn,
    VenuePublicationEvidenceIn,
)
from booker_api.security import (
    audit,
    authenticate_token,
    aware,
    bearer,
    current_user,
    ensure_admin_2fa_session,
    membership,
    now,
    require_admin,
    require_org_member,
    require_org_owner_or_admin_member,
    require_org_writer,
)
from booker_api.vacation import clear_vacation, set_vacation, vacation_status
from booker_api.venue_catalog import public_disclosure

router = APIRouter(tags=["catalog"])


def _bind_unambiguous_services(db: Session, org_id: str, profile_type: str, profile_id: str) -> None:
    profile_count = (
        db.query(Artist.id).filter(Artist.organization_id == org_id).count()
        + db.query(Venue.id).filter(Venue.organization_id == org_id).count()
    )
    if profile_count != 1:
        return
    if profile_type == "artist":
        profile = db.get(Artist, profile_id)
        category_code = profile.category if profile else None
    else:
        category_code = "venue"
    if category_code is None:
        return
    db.query(Service).filter(
        Service.organization_id == org_id,
        Service.category_code == category_code,
        Service.resource_type.is_(None),
        Service.resource_id.is_(None),
    ).update(
        {Service.resource_type: profile_type, Service.resource_id: profile_id},
        synchronize_session=False,
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
            VenuePhoto.photo_rights_status.in_(PUBLIC_MEDIA_RIGHTS),
            VenuePhoto.rights_attested_at.is_not(None),
            VenuePhoto.rights_attested_by_user_id.is_not(None),
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


def _private_venue_photos(db: Session, venue_id: str) -> list[dict]:
    rows = (
        db.query(VenuePhoto)
        .filter(VenuePhoto.venue_id == venue_id)
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
    return venue_publication_eligibility(db, venue).eligible


def _optional_user(
    request: FastAPIRequest,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    try:
        user, session = authenticate_token(db, creds.credentials)
        if user.is_support_operator and not user.is_platform_admin:
            # Optional auth must never grant a staff account private org projection.
            return None
        request.state.catalog_auth_session = session
        return user
    except HTTPException:
        return None


def _can_view_private_profile(
    request: FastAPIRequest, db: Session, user: User | None, organization_id: str
) -> bool:
    if user is None:
        return False
    if membership(db, user.id, organization_id):
        return True
    if not user.is_platform_admin:
        return False
    session = getattr(request.state, "catalog_auth_session", None)
    if session is None:
        return False
    try:
        ensure_admin_2fa_session(request, db, user, session, force=True)
    except HTTPException:
        return False
    return True


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
    db.flush()
    _bind_unambiguous_services(db, artist.organization_id, "artist", artist.id)
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
    _bind_unambiguous_services(db, venue.organization_id, "venue", venue.id)
    hall = VenueHall(venue_id=venue.id, name="Основной зал", capacity=body.capacity)
    db.add(hall)
    db.commit()
    db.refresh(venue)
    db.refresh(hall)
    return {"id": venue.id, "hall_id": hall.id}


@router.put("/artists/{artist_id}/publication-evidence")
@router.patch("/artists/{artist_id}/publication-evidence", include_in_schema=False)
def update_artist_publication_evidence(
    artist_id: str,
    body: ArtistPublicationEvidenceIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    require_org_owner_or_admin_member(db, user, artist.organization_id)
    if not body.rights_attested:
        raise HTTPException(400, "Нужно подтвердить права на медиа")
    artist.media_url = body.media_url
    artist.media_source_url = body.media_source_url
    artist.media_rights_status = body.media_rights_status
    artist.media_rights_attested_at = now()
    artist.media_rights_attested_by_user_id = user.id
    artist.calendar_confirmed_through = body.calendar_confirmed_through
    artist.calendar_confirmed_at = now()
    artist.calendar_confirmed_by_user_id = user.id
    audit(
        db,
        actor_user_id=user.id,
        action="artist.publication_evidence_updated",
        entity_type="artist",
        entity_id=artist.id,
        payload={
            "media_rights_status": body.media_rights_status,
            "calendar_confirmed_through": body.calendar_confirmed_through.isoformat(),
        },
    )
    db.commit()
    eligibility = artist_publication_eligibility(db, artist)
    return {"eligible": eligibility.eligible, "reason_codes": eligibility.reason_codes}


@router.put("/venues/{venue_id}/publication-evidence")
@router.patch("/venues/{venue_id}/publication-evidence", include_in_schema=False)
def update_venue_publication_evidence(
    venue_id: str,
    body: VenuePublicationEvidenceIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    require_org_owner_or_admin_member(db, user, venue.organization_id)
    venue.calendar_confirmed_through = body.calendar_confirmed_through
    venue.calendar_confirmed_at = now()
    venue.calendar_confirmed_by_user_id = user.id
    audit(
        db,
        actor_user_id=user.id,
        action="venue.publication_evidence_updated",
        entity_type="venue",
        entity_id=venue.id,
        payload={"calendar_confirmed_through": body.calendar_confirmed_through.isoformat()},
    )
    db.commit()
    eligibility = venue_publication_eligibility(db, venue)
    return {"eligible": eligibility.eligible, "reason_codes": eligibility.reason_codes}


@router.put("/venues/{venue_id}/photos", status_code=status.HTTP_200_OK)
@router.post("/venues/{venue_id}/photos", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def add_venue_photo(
    venue_id: str,
    body: VenuePhotoIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    require_org_owner_or_admin_member(db, user, venue.organization_id)
    if not body.rights_attested:
        raise HTTPException(400, "Нужно подтвердить права на фотографию")
    photo = (
        db.query(VenuePhoto)
        .filter(VenuePhoto.venue_id == venue.id, VenuePhoto.photo_url == body.photo_url)
        .one_or_none()
    )
    created = photo is None
    if photo is None:
        photo = VenuePhoto(venue_id=venue.id, photo_url=body.photo_url)
        db.add(photo)
    photo.photo_source_url = body.photo_source_url
    photo.photo_rights_status = body.photo_rights_status
    photo.rights_attested_at = now()
    photo.rights_attested_by_user_id = user.id
    photo.sort_order = body.sort_order
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="venue.photo_recorded",
        entity_type="venue_photo",
        entity_id=photo.id,
        payload={"venue_id": venue.id, "rights_status": body.photo_rights_status},
    )
    db.commit()
    return {"id": photo.id, "created": created}


def _set_publication_state(db: Session, target, body: PublicationStateIn, user: User) -> dict:
    require_org_owner_or_admin_member(db, user, target.organization_id)
    if target.publication_state_version != body.state_version:
        raise HTTPException(409, "Профиль изменён; обновите данные и повторите")
    previous = bool(target.publication_enabled)
    target.publication_enabled = body.enabled
    if isinstance(target, Artist):
        eligibility = artist_publication_eligibility(db, target)
        target_type = "artist"
    else:
        eligibility = venue_publication_eligibility(db, target)
        target_type = "venue"
    if body.enabled and not eligibility.eligible:
        target.publication_enabled = previous
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "Профиль пока нельзя опубликовать", "reason_codes": eligibility.reason_codes},
        )
    changed = previous != body.enabled
    if changed:
        target.publication_state_version += 1
        audit(
            db,
            actor_user_id=user.id,
            action=f"{target_type}.publication_changed",
            entity_type=target_type,
            entity_id=target.id,
            payload={"enabled": body.enabled, "previous": previous},
        )
        db.commit()
    return {
        "enabled": bool(target.publication_enabled),
        "state_version": target.publication_state_version,
        "eligible": eligibility.eligible,
        "reason_codes": eligibility.reason_codes,
    }


@router.put("/artists/{artist_id}/publication")
def set_artist_publication(
    artist_id: str,
    body: PublicationStateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    return _set_publication_state(db, artist, body, user)


@router.put("/venues/{venue_id}/publication")
def set_venue_publication(
    venue_id: str,
    body: PublicationStateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    return _set_publication_state(db, venue, body, user)


@router.get("/venues/{venue_id}/halls")
def list_halls(
    venue_id: str,
    request: FastAPIRequest,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    if not _venue_in_catalog(db, venue):
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
        if not _can_view_private_profile(request, db, user, venue.organization_id):
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
    if venue.calendar_confirmed_through is not None or venue.publication_enabled:
        venue.calendar_confirmed_through = None
        venue.calendar_confirmed_at = None
        venue.calendar_confirmed_by_user_id = None
        venue.publication_enabled = False
        venue.publication_state_version += 1
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
    db: Session = Depends(get_db),
):
    """В выдаче только профили с календарём. Занятые слоты не считаются свободными."""
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
    required_through = calendar_day_bounds(date)[1] if date else None
    results = []
    if include_artists:
        q = db.query(Artist).filter(Artist.city == city)
        if category and category != "venue":
            q = q.filter(Artist.category == category)
        for artist in q.all():
            if artist.id in excluded:
                continue
            if not artist_publication_eligibility(
                db, artist, required_through=required_through
            ).eligible:
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
            if not venue_publication_eligibility(
                db, venue, required_through=required_through
            ).eligible:
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
            hall_slots_by_id: dict[str, list[AvailabilitySlot]] = {}
            for hall in halls:
                if hall.id not in hall_ids:
                    continue
                hall_slots_by_id[hall.id] = (
                    db.query(AvailabilitySlot)
                    .filter(
                        AvailabilitySlot.resource_type == "hall",
                        AvailabilitySlot.resource_id == hall.id,
                    )
                    .all()
                )
            if not any(hall_slots_by_id.values()):
                continue
            open_future = [
                slot
                for slots_for_hall in hall_slots_by_id.values()
                for slot in open_slots_unmasked(
                    slots_for_hall, horizon_start=now(), horizon_end=now() + timedelta(days=30)
                )
            ]
            pool = open_future
            if date:
                day_start, day_end = calendar_day_bounds(date)
                pool = [
                    slot
                    for slots_for_hall in hall_slots_by_id.values()
                    for slot in open_slots_unmasked(
                        slots_for_hall, day_start=day_start, day_end=day_end
                    )
                ]
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


_SEARCH_PAGE_BATCH = 64
_SEARCH_PAGE_MAX_BATCHES = 8


def _search_page_fingerprint(filters: dict) -> str:
    encoded = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _search_page_cursor(fingerprint: str, key: tuple[str, str]) -> str:
    payload = {"v": 1, "f": fingerprint, "k": key[0], "i": key[1]}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _read_search_page_cursor(cursor: str | None, fingerprint: str) -> tuple[str, str] | None:
    if cursor is None:
        return None
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise HTTPException(400, "Некорректный cursor") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"v", "f", "k", "i"}
        or payload["v"] != 1
        or payload["f"] != fingerprint
        or not isinstance(payload["k"], str)
        or payload["k"] not in {"artist", "venue"}
        or not isinstance(payload["i"], str)
        or not 0 < len(payload["i"]) <= 36
    ):
        raise HTTPException(400, "Cursor не соответствует фильтрам")
    return payload["k"], payload["i"]


def _search_page_candidates(
    db: Session,
    *,
    city: str,
    category: str | None,
    include_artists: bool,
    include_venues: bool,
    after: tuple[str, str] | None,
) -> tuple[list[tuple[str, Artist | Venue]], bool]:
    """Read at most one bounded kind/id window; the extra row signals continuation."""
    rows: list[tuple[str, Artist | Venue]] = []
    # These predicates are necessary conditions of the canonical publication gate.
    # The gate still checks every selected row, including media and calendar evidence.
    if include_artists and (after is None or after[0] == "artist"):
        artists = db.query(Artist).filter(
            Artist.city == city,
            Artist.publication_enabled.is_(True),
            Artist.verified.is_(True),
            Artist.verified_status == "approved",
        )
        if category and category != "venue":
            artists = artists.filter(Artist.category == category)
        if after:
            artists = artists.filter(Artist.id > after[1])
        found = artists.order_by(Artist.id).limit(_SEARCH_PAGE_BATCH + 1).all()
        rows.extend(("artist", artist) for artist in found[:_SEARCH_PAGE_BATCH])
        if len(found) > _SEARCH_PAGE_BATCH:
            return rows, True
    remaining = _SEARCH_PAGE_BATCH - len(rows)
    if include_venues and remaining:
        venues = db.query(Venue).filter(
            Venue.city == city,
            Venue.publication_enabled.is_(True),
            Venue.verified.is_(True),
            Venue.verified_status == "approved",
            Venue.moderation_status == "published",
            Venue.is_claimed.is_(True),
        )
        if after and after[0] == "venue":
            venues = venues.filter(Venue.id > after[1])
        found = venues.order_by(Venue.id).limit(remaining + 1).all()
        rows.extend(("venue", venue) for venue in found[:remaining])
        return rows, len(found) > remaining
    if include_venues and rows and rows[-1][0] == "artist":
        return rows, (
            db.query(Venue.id)
            .filter(
                Venue.city == city,
                Venue.publication_enabled.is_(True),
                Venue.verified.is_(True),
                Venue.verified_status == "approved",
                Venue.moderation_status == "published",
                Venue.is_claimed.is_(True),
            )
            .first()
            is not None
        )
    return rows, False


def _search_page_related(
    db: Session, candidates: list[tuple[str, Artist | Venue]]
) -> tuple[dict, dict, dict, dict, dict]:
    """Batch data needed to render candidates; publication still uses the canonical gate."""
    artist_ids = [row.id for kind, row in candidates if kind == "artist"]
    venue_ids = [row.id for kind, row in candidates if kind == "venue"]
    halls: dict[str, list[VenueHall]] = defaultdict(list)
    artist_tariffs: dict[str, list[ArtistTariff]] = defaultdict(list)
    venue_tariffs: dict[str, list[VenueTariff]] = defaultdict(list)
    photos: dict[str, list[VenuePhoto]] = defaultdict(list)
    slots: dict[tuple[str, str], list[AvailabilitySlot]] = defaultdict(list)
    hall_ids: list[str] = []
    if venue_ids:
        for hall in db.query(VenueHall).filter(VenueHall.venue_id.in_(venue_ids)).all():
            halls[hall.venue_id].append(hall)
            hall_ids.append(hall.id)
        for tariff in db.query(VenueTariff).filter(VenueTariff.venue_id.in_(venue_ids)).all():
            venue_tariffs[tariff.venue_id].append(tariff)
        for photo in (
            db.query(VenuePhoto)
            .filter(
                VenuePhoto.venue_id.in_(venue_ids),
                VenuePhoto.photo_rights_status.in_(PUBLIC_MEDIA_RIGHTS),
                VenuePhoto.rights_attested_at.is_not(None),
                VenuePhoto.rights_attested_by_user_id.is_not(None),
            )
            .order_by(VenuePhoto.venue_id, VenuePhoto.sort_order, VenuePhoto.id)
            .all()
        ):
            photos[photo.venue_id].append(photo)
    if artist_ids:
        for tariff in db.query(ArtistTariff).filter(ArtistTariff.artist_id.in_(artist_ids)).all():
            artist_tariffs[tariff.artist_id].append(tariff)
    slot_filters = []
    if artist_ids:
        slot_filters.append(and_(AvailabilitySlot.resource_type == "artist", AvailabilitySlot.resource_id.in_(artist_ids)))
    if hall_ids:
        slot_filters.append(and_(AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id.in_(hall_ids)))
    if slot_filters:
        for slot in db.query(AvailabilitySlot).filter(or_(*slot_filters)).all():
            slots[(slot.resource_type, slot.resource_id)].append(slot)
    return halls, artist_tariffs, venue_tariffs, photos, slots


@router.get("/catalog/search-page")
def search_catalog_page(
    city: str = Query("Москва"),
    category: str | None = None,
    date: datetime | None = None,
    exclude: str | None = None,
    format: str | None = None,
    travel: bool | None = None,
    budget_max: int | None = Query(None, ge=0),
    guests: int | None = Query(None, ge=1),
    seating: str | None = None,
    kind: str | None = None,
    limit: int = Query(24, ge=1, le=50),
    cursor: str | None = Query(None, max_length=2048),
    db: Session = Depends(get_db),
):
    """Bounded public search in stable artist/id then venue/id order."""
    excluded = sorted({item.strip() for item in (exclude or "").split(",") if item.strip()})
    kind_l = (kind or "").strip().lower() or None
    format_l = (format or "").strip().lower() or None
    seating_l = (seating or "").strip().lower() or None
    filters = {
        "city": city, "category": category, "date": aware(date).isoformat() if date else None,
        "exclude": excluded, "format": format_l, "travel": travel, "budget_max": budget_max,
        "guests": guests, "seating": seating_l, "kind": kind_l,
    }
    fingerprint = _search_page_fingerprint(filters)
    after = _read_search_page_cursor(cursor, fingerprint)
    include_artists = kind_l != "venue" and (not category or category != "venue")
    include_venues = kind_l != "artist" and (not category or category == "venue")
    if category == "venue":
        include_artists, include_venues = False, True
    elif category and kind_l != "venue":
        include_venues = kind_l == "venue"
    horizon_start = now()
    horizon_end = horizon_start + timedelta(days=30)
    day_start, day_end = calendar_day_bounds(date) if date else (None, None)
    results: list[dict] = []
    venues_out: list[dict] = []
    accepted = 0
    has_more = False
    for _ in range(_SEARCH_PAGE_MAX_BATCHES):
        candidates, batch_more = _search_page_candidates(
            db, city=city, category=category, include_artists=include_artists,
            include_venues=include_venues, after=after,
        )
        if not candidates:
            break
        halls, artist_tariffs, venue_tariffs, photos, slots = _search_page_related(db, candidates)
        eligibility = batch_publication_eligibility(
            db,
            [row for resource_type, row in candidates if resource_type == "artist"],
            [row for resource_type, row in candidates if resource_type == "venue"],
            required_through=day_end,
        )
        for index, (resource_type, row) in enumerate(candidates):
            after = resource_type, row.id
            if row.id in excluded:
                continue
            if resource_type == "artist":
                if not eligibility[(resource_type, row.id)].eligible:
                    continue
                rider = _parse_rider(row.rider_json)
                if format_l and not _format_matches(rider, format_l):
                    continue
                travel_ok = _rider_travel_ok(rider)
                if travel is True and travel_ok is not True:
                    continue
                if travel is False and travel_ok is True:
                    continue
                resource_slots = slots[("artist", row.id)]
                if not resource_slots:
                    continue
                future = open_slots_unmasked(resource_slots, horizon_start=horizon_start, horizon_end=horizon_end)
                pool = open_slots_unmasked(resource_slots, day_start=day_start, day_end=day_end) if date else future
                if not pool:
                    continue
                tariffs = artist_tariffs[row.id]
                if budget_max is not None:
                    floor = _min_tariff(tariffs)
                    if floor is None or floor > budget_max:
                        continue
                nxt = min(pool, key=lambda slot: aware(slot.starts_at))
                results.append({
                    "id": row.id, "name": row.name, "city": row.city, "category": row.category,
                    "verified": row.verified, "has_calendar": True, "open_slots": len(pool),
                    "next_open_at": _catalog_iso(nxt.starts_at),
                    "search_date": aware(date).date().isoformat() if date else None,
                    "travel_ok": travel_ok, "formats": _rider_formats(rider),
                    "tariffs": [{"id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub} for t in tariffs],
                })
            else:
                if not eligibility[(resource_type, row.id)].eligible:
                    continue
                venue_halls = halls[row.id]
                matching = [h for h in venue_halls if (h.capacity or 0) >= guests] if guests is not None else list(venue_halls)
                if seating_l:
                    blob = " ".join([row.description or "", row.name or "", *[h.name for h in matching]]).lower()
                    if seating_l not in blob:
                        continue
                if guests is not None and not matching:
                    continue
                hall_ids = {h.id for h in matching} if guests is not None else {h.id for h in venue_halls}
                hall_slots = [slots[("hall", hall.id)] for hall in venue_halls if hall.id in hall_ids]
                if not any(hall_slots):
                    continue
                future = [slot for group in hall_slots for slot in open_slots_unmasked(group, horizon_start=horizon_start, horizon_end=horizon_end)]
                pool = [slot for group in hall_slots for slot in open_slots_unmasked(group, day_start=day_start, day_end=day_end)] if date else future
                if not pool:
                    continue
                tariffs = venue_tariffs[row.id]
                if budget_max is not None and kind_l == "venue":
                    floor = _min_tariff(tariffs)
                    if floor is not None and floor > budget_max:
                        continue
                first_photo = photos[row.id][0] if photos[row.id] else None
                nxt = min(pool, key=lambda slot: aware(slot.starts_at))
                venues_out.append({
                    "id": row.id, "name": row.name, "city": row.city, "category": "venue",
                    "verified": row.verified, "address": row.address or "", "metro": row.metro or "",
                    "availability_mode": row.availability_mode or "owner",
                    "listing_origin": row.listing_origin or "owner", "source_type": row.source_type,
                    "partnership_status": row.partnership_status, "public_disclosure": public_disclosure(row),
                    "capacity": row.capacity, "matching_halls": [_hall_item(h) for h in matching],
                    "open_slots": len(pool), "next_open_at": _catalog_iso(nxt.starts_at),
                    "tariffs": [{"honorarium_rub": t.honorarium_rub} for t in tariffs],
                    "cover_photo": ({"url": first_photo.photo_url, "source_url": first_photo.photo_source_url,
                                     "rights_status": first_photo.photo_rights_status} if first_photo else None),
                })
            accepted += 1
            if accepted == limit:
                has_more = index + 1 < len(candidates) or batch_more
                break
        if accepted == limit:
            break
        has_more = batch_more
        if not batch_more:
            break
    return {
        "items": results, "venues": venues_out, "has_more": has_more,
        "next_cursor": _search_page_cursor(fingerprint, after) if has_more and after else None,
    }


@router.get("/catalog/public-index")
def list_public_catalog_index(
    cursor: str | None = Query(None, description="Opaque kind:id cursor from next_cursor"),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Stable, exhaustive index of profiles that anonymous visitors may open.

    Sitemap generation must not infer publication from a filtered search page.
    The cursor is the last emitted key, so an unpublished row disappearing
    between requests does not invalidate the next page.
    """
    after: tuple[str, str] | None = None
    if cursor:
        kind, separator, resource_id = cursor.partition(":")
        if separator != ":" or kind not in {"artist", "venue"} or not resource_id:
            raise HTTPException(400, "Некорректный cursor")
        after = (kind, resource_id)

    rows: list[tuple[str, str]] = []
    for artist in db.query(Artist).order_by(Artist.id).all():
        if artist_publication_eligibility(db, artist).eligible:
            rows.append(("artist", artist.id))
    for venue in db.query(Venue).order_by(Venue.id).all():
        if venue_publication_eligibility(db, venue).eligible:
            rows.append(("venue", venue.id))

    if after is not None:
        rows = [row for row in rows if row > after]
    page = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = f"{page[-1][0]}:{page[-1][1]}" if has_more and page else None
    return {
        "items": [{"type": kind, "id": resource_id} for kind, resource_id in page],
        "next_cursor": next_cursor,
    }


@router.get("/catalog/public-status/{resource_type}/{resource_id}", status_code=204)
def public_profile_status(
    resource_type: str,
    resource_id: str,
    db: Session = Depends(get_db),
):
    """Cheap publication preflight for the web edge before streamed rendering."""
    if resource_type == "artist":
        resource = db.get(Artist, resource_id)
        eligible = bool(resource and artist_publication_eligibility(db, resource).eligible)
    elif resource_type == "venue":
        resource = db.get(Venue, resource_id)
        eligible = bool(resource and venue_publication_eligibility(db, resource).eligible)
    else:
        raise HTTPException(404, "Профиль не найден")
    if not eligible:
        raise HTTPException(404, "Профиль не найден")
    return Response(status_code=204)


@router.get("/catalog/demo/venues")
def list_investor_demo_venues(
    city: str = Query("Москва"),
    limit: int = Query(300, ge=1, le=500),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Research cards for authenticated platform administrators only.

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
def get_venue(
    venue_id: str,
    request: FastAPIRequest,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    can_view_private = _can_view_private_profile(request, db, user, venue.organization_id)
    if not venue_publication_eligibility(db, venue).eligible and not can_view_private:
        raise HTTPException(404, "Площадка не найдена")
    halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()
    tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all()
    photos = (
        _private_venue_photos(db, venue.id)
        if can_view_private
        else _public_venue_photos(db, venue.id)
    )
    slots = []
    for hall in halls:
        hall_slots = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.resource_type == "hall", AvailabilitySlot.resource_id == hall.id)
            .order_by(AvailabilitySlot.starts_at)
            .all()
        )
        public_open_ids = {s.id for s in open_slots_unmasked(hall_slots)}
        for s in hall_slots:
            if can_view_private or s.id in public_open_ids:
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
        "details": json.loads(venue.details_json or "{}") if can_view_private else {},
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
def get_artist(
    artist_id: str,
    request: FastAPIRequest,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    can_view_private = _can_view_private_profile(request, db, user, artist.organization_id)
    if not artist_publication_eligibility(db, artist).eligible and not can_view_private:
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
    public_open_ids = {slot.id for slot in open_slots_unmasked(slots)}
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
            _slot_item(s)
            for s in slots
            if can_view_private or s.id in public_open_ids
        ],
    }
