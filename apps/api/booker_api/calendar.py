from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from booker_api.models import AvailabilitySlot
from booker_api.security import aware

MSK = ZoneInfo("Europe/Moscow")


def ranges_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return aware(a_start) < aware(b_end) and aware(b_start) < aware(a_end)


def calendar_day_bounds(dt: datetime) -> tuple[datetime, datetime]:
    """Границы календарного дня в Москве, независимо от таймзоны входящей даты."""
    local = aware(dt).astimezone(MSK)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def overlapping_slots(
    db: Session,
    resource_type: str,
    resource_id: str,
    starts_at: datetime,
    ends_at: datetime,
    *,
    statuses: tuple[str, ...] = ("open", "held", "confirmed"),
    exclude_id: str | None = None,
) -> list[AvailabilitySlot]:
    q = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.resource_type == resource_type,
        AvailabilitySlot.resource_id == resource_id,
        AvailabilitySlot.status.in_(statuses),
    )
    if exclude_id:
        q = q.filter(AvailabilitySlot.id != exclude_id)
    found: list[AvailabilitySlot] = []
    for slot in q.all():
        if ranges_overlap(starts_at, ends_at, slot.starts_at, slot.ends_at):
            found.append(slot)
    return found
