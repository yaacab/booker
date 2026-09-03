"""Import busy intervals from iCal into availability slots."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.calendar import ranges_overlap
from booker_api.ical import IcalEvent, fetch_ical, parse_ical_events
from booker_api.models import Artist, AvailabilitySlot, Venue, VenueHall
from booker_api.security import audit, aware, now


def calendar_targets(db: Session, org_id: str, kind: str) -> list[dict]:
    items: list[dict] = []
    if kind == "artist":
        artist = db.query(Artist).filter(Artist.organization_id == org_id).first()
        if artist:
            items.append(
                {
                    "resource_type": "artist",
                    "resource_id": artist.id,
                    "label": artist.name,
                }
            )
    elif kind == "venue":
        venue = db.query(Venue).filter(Venue.organization_id == org_id).first()
        if venue:
            halls = db.query(VenueHall).filter(VenueHall.venue_id == venue.id).order_by(VenueHall.name).all()
            for hall in halls:
                items.append(
                    {
                        "resource_type": "hall",
                        "resource_id": hall.id,
                        "label": f"{venue.name} · {hall.name}",
                        "venue_id": venue.id,
                    }
                )
            if not halls:
                items.append(
                    {
                        "resource_type": "venue",
                        "resource_id": venue.id,
                        "label": venue.name,
                        "venue_id": venue.id,
                    }
                )
    return items


def _resolve_resource(db: Session, org_id: str, resource_type: str, resource_id: str) -> None:
    if resource_type == "artist":
        artist = db.get(Artist, resource_id)
        if not artist or artist.organization_id != org_id:
            raise ValueError("Артист не найден")
        return
    if resource_type == "hall":
        hall = db.get(VenueHall, resource_id)
        if not hall:
            raise ValueError("Зал не найден")
        venue = db.get(Venue, hall.venue_id)
        if not venue or venue.organization_id != org_id:
            raise ValueError("Зал не найден")
        return
    raise ValueError("resource_type: artist|hall")


def _clear_previous_ical(db: Session, resource_type: str, resource_id: str) -> int:
    rows = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == resource_type,
            AvailabilitySlot.resource_id == resource_id,
            AvailabilitySlot.status == "busy",
            AvailabilitySlot.external_uid.like("ical:%"),
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    return len(rows)


def _remove_open_overlaps(
    db: Session,
    resource_type: str,
    resource_id: str,
    starts_at,
    ends_at,
) -> int:
    removed = 0
    open_rows = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == resource_type,
            AvailabilitySlot.resource_id == resource_id,
            AvailabilitySlot.status == "open",
        )
        .all()
    )
    for row in open_rows:
        if ranges_overlap(row.starts_at, row.ends_at, starts_at, ends_at):
            db.delete(row)
            removed += 1
    return removed


def import_busy_events(
    db: Session,
    *,
    org_id: str,
    resource_type: str,
    resource_id: str,
    events: list[IcalEvent],
    actor_user_id: str,
) -> dict:
    _resolve_resource(db, org_id, resource_type, resource_id)
    replaced = _clear_previous_ical(db, resource_type, resource_id)
    imported = 0
    skipped = 0
    removed_open = 0
    current = now()

    for event in events:
        if event.cancelled or event.transparent:
            skipped += 1
            continue
        if aware(event.ends_at) <= current:
            skipped += 1
            continue
        if aware(event.starts_at) >= aware(event.ends_at):
            skipped += 1
            continue
        removed_open += _remove_open_overlaps(
            db, resource_type, resource_id, event.starts_at, event.ends_at
        )
        slot = AvailabilitySlot(
            resource_type=resource_type,
            resource_id=resource_id,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            status="busy",
            external_uid=f"ical:{event.uid}",
        )
        db.add(slot)
        imported += 1

    audit(
        db,
        actor_user_id=actor_user_id,
        action="calendar.ical_imported",
        entity_type="slot",
        entity_id=resource_id,
        payload={
            "resource_type": resource_type,
            "imported": imported,
            "skipped": skipped,
            "replaced": replaced,
            "removed_open": removed_open,
        },
    )
    db.commit()
    return {
        "imported": imported,
        "skipped": skipped,
        "replaced": replaced,
        "removed_open": removed_open,
    }


async def import_ical_source(
    db: Session,
    *,
    org_id: str,
    resource_type: str,
    resource_id: str,
    ical_url: str | None,
    ical_body: str | None,
    actor_user_id: str,
) -> dict:
    if ical_url:
        body = await fetch_ical(ical_url)
    elif ical_body:
        body = ical_body
    else:
        raise ValueError("Нужен ical_url или ical_body")
    events = parse_ical_events(body)
    return import_busy_events(
        db,
        org_id=org_id,
        resource_type=resource_type,
        resource_id=resource_id,
        events=events,
        actor_user_id=actor_user_id,
    )
