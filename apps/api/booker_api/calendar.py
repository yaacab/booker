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
    buffer_before_min: int = 0,
    buffer_after_min: int = 0,
) -> list[AvailabilitySlot]:
    incoming_start = starts_at - timedelta(minutes=max(0, buffer_before_min or 0))
    incoming_end = ends_at + timedelta(minutes=max(0, buffer_after_min or 0))
    q = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.resource_type == resource_type,
        AvailabilitySlot.resource_id == resource_id,
        AvailabilitySlot.status.in_(statuses),
    )
    if exclude_id:
        q = q.filter(AvailabilitySlot.id != exclude_id)
    found: list[AvailabilitySlot] = []
    for slot in q.all():
        before = max(0, getattr(slot, "buffer_before_min", 0) or 0)
        after = max(0, getattr(slot, "buffer_after_min", 0) or 0)
        slot_start = slot.starts_at - timedelta(minutes=before)
        slot_end = slot.ends_at + timedelta(minutes=after)
        if ranges_overlap(incoming_start, incoming_end, slot_start, slot_end):
            found.append(slot)
    return found
