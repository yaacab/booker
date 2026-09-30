"""On-demand fixtures exclusively for the isolated demo SQLite database."""
import os
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from booker_api.calendar import calendar_day_bounds, overlapping_slots
from booker_api.models import Artist, AvailabilitySlot, VenueHall


def ensure_demo_day(db: Session, date: datetime) -> None:
    if os.environ.get("BOOKER_DEMO_OPEN_CALENDAR") != "1":
        return
    url = db.get_bind().url
    path = Path(url.database or "").resolve()
    if url.get_backend_name() != "sqlite" or path != Path("/var/lib/booker-demo/demo.db"):
        raise RuntimeError("Demo calendar requires the isolated /var/lib/booker-demo/demo.db")
    start, end = calendar_day_bounds(date)
    resources = [("artist", row.id) for row in db.query(Artist).all()]
    resources += [("hall", row.id) for row in db.query(VenueHall).all()]
    for kind, resource_id in resources:
        # Never erase holds, bookings, busy dates, or an existing calendar.
        if overlapping_slots(db, kind, resource_id, start, end):
            continue
        slot_id = str(uuid5(NAMESPACE_URL, f"booker-demo:{kind}:{resource_id}:{start.date()}"))
        db.execute(insert(AvailabilitySlot).values(
            id=slot_id, resource_type=kind, resource_id=resource_id,
            starts_at=start, ends_at=end, status="open",
            buffer_before_min=0, buffer_after_min=0,
            external_uid=f"demo:{start.date()}",
        ).on_conflict_do_nothing(index_elements=["id"]))
    db.commit()
