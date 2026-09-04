"""Vacation mode: mark artist/hall unavailable for a date range.

Vacation is a busy overlay over local open slots (same semantics as iCal busy):
open rows are preserved and become visible again after clear.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from booker_api.ical_import import _count_open_overlaps, _resolve_resource, calendar_targets
from booker_api.models import AvailabilitySlot
from booker_api.security import audit, aware, now

VACATION_UID = "vacation:active"


def _vacation_slot(
    db: Session,
    resource_type: str,
    resource_id: str,
) -> AvailabilitySlot | None:
    return (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_type == resource_type,
            AvailabilitySlot.resource_id == resource_id,
            AvailabilitySlot.status == "busy",
            AvailabilitySlot.external_uid.like("vacation:%"),
        )
        .order_by(AvailabilitySlot.starts_at.desc())
        .first()
    )


def set_vacation(
    db: Session,
    *,
    org_id: str,
    resource_type: str,
    resource_id: str,
    starts_at: datetime,
    ends_at: datetime,
    actor_user_id: str,
) -> dict:
    _resolve_resource(db, org_id, resource_type, resource_id)
    start = aware(starts_at)
    end = aware(ends_at)
    if start >= end:
        raise ValueError("Дата окончания должна быть позже начала")
    if end <= now():
        raise ValueError("Отпуск должен заканчиваться в будущем")

    previous = _vacation_slot(db, resource_type, resource_id)
    if previous:
        db.delete(previous)

    overlaid_open = _count_open_overlaps(db, resource_type, resource_id, start, end)
    slot = AvailabilitySlot(
        resource_type=resource_type,
        resource_id=resource_id,
        starts_at=start,
        ends_at=end,
        status="busy",
        external_uid=VACATION_UID,
    )
    db.add(slot)
    audit(
        db,
        actor_user_id=actor_user_id,
        action="calendar.vacation_set",
        entity_type="slot",
        entity_id=resource_id,
        payload={
            "resource_type": resource_type,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "overlaid_open": overlaid_open,
            "removed_open": overlaid_open,
        },
    )
    db.commit()
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
        "overlaid_open": overlaid_open,
        "removed_open": overlaid_open,
    }


def clear_vacation(
    db: Session,
    *,
    org_id: str,
    resource_type: str,
    resource_id: str,
    actor_user_id: str,
) -> dict:
    _resolve_resource(db, org_id, resource_type, resource_id)
    row = _vacation_slot(db, resource_type, resource_id)
    if not row:
        return {"cleared": False}
    db.delete(row)
    audit(
        db,
        actor_user_id=actor_user_id,
        action="calendar.vacation_cleared",
        entity_type="slot",
        entity_id=resource_id,
        payload={"resource_type": resource_type},
    )
    db.commit()
    return {"cleared": True}


def vacation_status(db: Session, org_id: str, kind: str) -> dict:
    items: list[dict] = []
    for target in calendar_targets(db, org_id, kind):
        row = _vacation_slot(db, target["resource_type"], target["resource_id"])
        active = row is not None and aware(row.ends_at) > now()
        items.append(
            {
                **target,
                "active": active,
                "starts_at": row.starts_at.isoformat() if row else None,
                "ends_at": row.ends_at.isoformat() if row else None,
            }
        )
    return {"items": items}
