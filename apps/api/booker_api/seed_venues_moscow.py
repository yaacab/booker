"""Idempotent import of curated Moscow open-data venues into the catalog.

Creates shared org «Букер · открытый каталог Москва», venues with halls,
optional tariff hints, and synthetic open slots (30d for curated tariff rows,
14d for bulk open-data).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from booker_api.db import SessionLocal, engine, init_schema
from booker_api.models import (
    AvailabilitySlot,
    Organization,
    TeamMember,
    User,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.security import audit, hash_password, now

MSK = timezone(timedelta(hours=3))
OPEN_CATALOG_ORG = "Букер · открытый каталог Москва"
IMPORT_USER_EMAIL = "open-catalog@booker.local"
DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "moscow_venues_open.json"
# Fallback when running from apps/api cwd
_ALT_DATA = Path(__file__).resolve().parents[2].parent / "data" / "moscow_venues_open.json"


def _data_file() -> Path:
    if DATA_PATH.is_file():
        return DATA_PATH
    if _ALT_DATA.is_file():
        return _ALT_DATA
    # repo root relative to apps/api package
    root = Path(__file__).resolve().parents[3]
    candidate = root / "data" / "moscow_venues_open.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"moscow_venues_open.json not found near {DATA_PATH}")


def _load_payload() -> dict:
    return json.loads(_data_file().read_text(encoding="utf-8"))


def _ensure_shared_org(db: Session) -> tuple[Organization, User]:
    org = db.query(Organization).filter(Organization.name == OPEN_CATALOG_ORG).one_or_none()
    user = db.query(User).filter(User.email == IMPORT_USER_EMAIL).one_or_none()
    if not user:
        user = User(
            email=IMPORT_USER_EMAIL,
            full_name="Букер Open Catalog",
            phone="+79000000000",
            # Сервисная учётка без интерактивного логина: случайный пароль.
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.flush()
    if not org:
        org = Organization(name=OPEN_CATALOG_ORG, kind="venue", city="Москва")
        db.add(org)
        db.flush()
        db.add(
            TeamMember(
                user_id=user.id,
                organization_id=org.id,
                role="owner",
                can_confirm_offer=True,
            )
        )
    return org, user


def _find_existing(db: Session, *, name: str, source_url: str, org_id: str) -> Venue | None:
    if source_url:
        hit = (
            db.query(Venue)
            .filter(Venue.organization_id == org_id, Venue.source_url == source_url)
            .one_or_none()
        )
        if hit:
            return hit
    return (
        db.query(Venue)
        .filter(Venue.organization_id == org_id, Venue.name == name)
        .one_or_none()
    )


def _synthetic_slots(db: Session, hall_id: str, *, days: int = 30) -> int:
    """Ensure evening open slots for the next `days` calendar days (MSK)."""
    created = 0
    base = now().astimezone(MSK).date()
    for offset in range(1, days + 1):
        day = base + timedelta(days=offset)
        uid = f"synthetic:open:{day.isoformat()}"
        exists = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_type == "hall",
                AvailabilitySlot.resource_id == hall_id,
                AvailabilitySlot.external_uid == uid,
            )
            .one_or_none()
        )
        if exists:
            if exists.status != "open":
                continue
            continue
        starts = datetime(day.year, day.month, day.day, 18, 0, tzinfo=MSK)
        ends = datetime(day.year, day.month, day.day, 22, 0, tzinfo=MSK)
        db.add(
            AvailabilitySlot(
                resource_type="hall",
                resource_id=hall_id,
                starts_at=starts,
                ends_at=ends,
                status="open",
                external_uid=uid,
            )
        )
        created += 1
    return created


def import_moscow_venues(db: Session) -> dict:
    payload = _load_payload()
    org, user = _ensure_shared_org(db)
    venues_in = payload.get("venues") or []
    created_venues = 0
    updated_venues = 0
    slots_created = 0

    for row in venues_in:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        source_url = str(row.get("source_url") or "").strip()
        venue = _find_existing(db, name=name, source_url=source_url, org_id=org.id)
        capacity = int(row.get("capacity") or 100)
        fields = {
            "address": str(row.get("address") or ""),
            "district": str(row.get("district") or ""),
            "metro": str(row.get("metro") or ""),
            "description": str(row.get("description") or ""),
            "source_url": source_url,
            "source_attribution": str(row.get("attribution") or "openstreetmap"),
            "listing_origin": "open_data",
            "availability_mode": "synthetic",
            "city": "Москва",
            "capacity": capacity,
            "verified": False,
            "verified_status": "pending",
        }
        if venue is None:
            venue = Venue(organization_id=org.id, name=name, **fields)
            db.add(venue)
            db.flush()
            hall = VenueHall(venue_id=venue.id, name="Основной зал", capacity=capacity)
            db.add(hall)
            db.flush()
            created_venues += 1
            audit(
                db,
                actor_user_id=user.id,
                action="venue.open_data_imported",
                entity_type="venue",
                entity_id=venue.id,
                payload={"name": name, "source_url": source_url},
            )
        else:
            for key, value in fields.items():
                setattr(venue, key, value)
            hall = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).order_by(VenueHall.name).first()
            if not hall:
                hall = VenueHall(venue_id=venue.id, name="Основной зал", capacity=capacity)
                db.add(hall)
                db.flush()
            else:
                hall.capacity = capacity
            updated_venues += 1

        tariff_from = row.get("tariff_from_rub")
        if tariff_from is not None:
            try:
                amount = int(tariff_from)
            except (TypeError, ValueError):
                amount = None
            if amount and amount > 0:
                tariff = (
                    db.query(VenueTariff)
                    .filter(VenueTariff.venue_id == venue.id, VenueTariff.title == "Аренда (ориентир)")
                    .one_or_none()
                )
                if tariff is None:
                    db.add(
                        VenueTariff(
                            venue_id=venue.id,
                            title="Аренда (ориентир)",
                            honorarium_rub=amount,
                        )
                    )
                else:
                    tariff.honorarium_rub = amount

        hall = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).order_by(VenueHall.name).first()
        assert hall is not None
        # Curated wave-1 (with tariff hint) keeps 30d; OSM/mos bulk uses 14d to limit DB size.
        slot_days = 30 if row.get("tariff_from_rub") is not None else 14
        slots_created += _synthetic_slots(db, hall.id, days=slot_days)

    db.commit()
    return {
        "org_id": org.id,
        "created_venues": created_venues,
        "updated_venues": updated_venues,
        "slots_created": slots_created,
        "total_in_file": len(venues_in),
    }


def main() -> None:
    init_schema(engine)
    db = SessionLocal()
    try:
        print(import_moscow_venues(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
