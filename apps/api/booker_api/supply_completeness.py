"""Supply profile completeness for artist/venue organizations."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Organization,
    Service,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.security import now


def _slot_window_end():
    return now() + timedelta(days=30)


def supply_completeness(db: Session, org: Organization) -> dict:
    if org.kind not in {"artist", "venue"}:
        return {"score": 100, "items": [], "applicable": False}

    items: list[dict] = []
    window_end = _slot_window_end()

    if org.kind == "artist":
        artist = db.query(Artist).filter(Artist.organization_id == org.id).first()
        items.append(
            {
                "id": "catalog_profile",
                "label": "Профиль в каталоге",
                "done": artist is not None,
            }
        )
        items.append(
            {
                "id": "verified",
                "label": "Верификация пройдена",
                "done": bool(artist and artist.verified),
            }
        )
        resource_ids = [artist.id] if artist else []
        tariffs = (
            db.query(ArtistTariff).filter(ArtistTariff.artist_id == artist.id).all() if artist else []
        )
    else:
        venue = db.query(Venue).filter(Venue.organization_id == org.id).first()
        items.append(
            {
                "id": "catalog_profile",
                "label": "Площадка в каталоге",
                "done": venue is not None,
            }
        )
        items.append(
            {
                "id": "verified",
                "label": "Верификация пройдена",
                "done": bool(venue and venue.verified),
            }
        )
        hall_ids = [h.id for h in db.query(VenueHall).filter(VenueHall.venue_id == venue.id).all()] if venue else []
        resource_ids = hall_ids
        tariffs = db.query(VenueTariff).filter(VenueTariff.venue_id == venue.id).all() if venue else []
        items.append(
            {
                "id": "halls",
                "label": "Есть зал",
                "done": len(hall_ids) > 0,
            }
        )

    service_count = db.query(Service).filter(Service.organization_id == org.id).count()
    items.append(
        {
            "id": "services",
            "label": "Услуга в кабинете",
            "done": service_count > 0,
        }
    )
    items.append(
        {
            "id": "tariffs",
            "label": "Тариф с гонораром",
            "done": any(t.honorarium_rub > 0 for t in tariffs),
        }
    )
    open_slots = 0
    if resource_ids:
        open_slots = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_id.in_(resource_ids),
                AvailabilitySlot.status == "open",
                AvailabilitySlot.starts_at >= now(),
                AvailabilitySlot.starts_at <= window_end,
            )
            .count()
        )
    items.append(
        {
            "id": "calendar_30d",
            "label": "Открытый слот на 30 дней",
            "done": open_slots > 0,
        }
    )

    done_count = sum(1 for item in items if item["done"])
    score = round(100 * done_count / len(items)) if items else 0
    return {"score": score, "items": items, "applicable": True}
