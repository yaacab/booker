"""Optional operator-approved working-time deadlines for support first response."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from booker_api.config import settings
from booker_api.security import aware

logger = logging.getLogger(__name__)


def _window(day: date, hour: str, zone: ZoneInfo) -> datetime:
    if not isinstance(hour, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hour):
        raise ValueError("Support SLA hours must use HH:MM without offset")
    parsed = time.fromisoformat(hour)
    local = datetime.combine(day, parsed)
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("Ambiguous or missing support SLA boundary")
    utc = first.astimezone(timezone.utc)
    if utc.astimezone(zone).replace(tzinfo=None) != local:
        raise ValueError("Missing support SLA boundary")
    return utc


def support_response_due_at(
    urgency_code: str | None,
    minutes: int | None,
    *,
    started_at: datetime,
) -> datetime | None:
    """Return no public deadline unless this urgency has an explicit calendar."""

    if not urgency_code or minutes is None:
        return None
    if not settings.support_sla_schedule_json:
        logger.error("Invalid support SLA schedule: empty override")
        return None
    try:
        schedules = json.loads(settings.support_sla_schedule_json)
        schedule = schedules[urgency_code]
        zone = ZoneInfo(schedule["timezone"])
        weekdays = set(schedule["weekdays"])
        if not weekdays or any(type(day) is not int or day not in range(7) for day in weekdays):
            raise ValueError("Invalid support SLA weekdays")
        closed_dates = {date.fromisoformat(value) for value in schedule["closed_dates"]}
        start_hour = schedule["start"]
        end_hour = schedule["end"]
        if time.fromisoformat(start_hour) >= time.fromisoformat(end_hour):
            raise ValueError("Invalid support SLA window")
        cursor = aware(started_at).astimezone(timezone.utc)
        remaining = timedelta(minutes=minutes)
        first_day = cursor.astimezone(zone).date()
        for offset in range(730):
            day = first_day + timedelta(days=offset)
            if day.weekday() not in weekdays or day in closed_dates:
                continue
            start = _window(day, start_hour, zone)
            end = _window(day, end_hour, zone)
            if start.astimezone(zone).utcoffset() != end.astimezone(zone).utcoffset():
                raise ValueError("Support SLA window crosses a timezone transition")
            segment_start = max(cursor, start)
            if segment_start >= end:
                continue
            available = end - segment_start
            if remaining <= available:
                return segment_start + remaining
            remaining -= available
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Invalid support SLA schedule: %s", type(exc).__name__)
    return None
