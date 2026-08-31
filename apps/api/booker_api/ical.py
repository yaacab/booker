"""Minimal iCalendar (RFC 5545) parser for busy-time import."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from booker_api.security import aware

MSK = ZoneInfo("Europe/Moscow")
MAX_ICAL_BYTES = 512_000
ICAL_FETCH_TIMEOUT = 10.0


@dataclass(frozen=True)
class IcalEvent:
    uid: str
    starts_at: datetime
    ends_at: datetime
    cancelled: bool = False
    transparent: bool = False


def unfold_ical(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in raw.split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _split_property(line: str) -> tuple[str, dict[str, str], str]:
    if ":" not in line:
        return line.upper(), {}, ""
    head, value = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        params[key.upper()] = raw.strip('"')
    return name, params, value.strip()


def _parse_datetime(value: str, params: dict[str, str]) -> datetime:
    tz_name = params.get("TZID")
    if re.fullmatch(r"\d{8}", value):
        parsed = datetime.strptime(value, "%Y%m%d").replace(tzinfo=MSK)
        return parsed
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
        return aware(dt)
    dt = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=MSK)
    if tz_name:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            dt = dt.replace(tzinfo=MSK)
    else:
        dt = dt.replace(tzinfo=MSK)
    return aware(dt)


def _parse_duration(value: str) -> timedelta:
    if not value.startswith("P"):
        raise ValueError(f"Bad DURATION: {value}")
    rest = value[1:]
    days = 0
    if "D" in rest:
        day_part, rest = rest.split("D", 1)
        days = int(day_part or 0)
    hours = minutes = seconds = 0
    if rest.startswith("T"):
        rest = rest[1:]
        for unit, mult in (("H", 3600), ("M", 60), ("S", 1)):
            if unit in rest:
                chunk, rest = rest.split(unit, 1)
                val = int(chunk or 0)
                if unit == "H":
                    hours = val
                elif unit == "M":
                    minutes = val
                else:
                    seconds = val
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def parse_ical_events(body: str) -> list[IcalEvent]:
    lines = unfold_ical(body)
    events: list[IcalEvent] = []
    in_event = False
    props: dict[str, list[tuple[dict[str, str], str]]] = {}

    def flush() -> None:
        nonlocal props
        uid_rows = props.get("UID", [])
        start_rows = props.get("DTSTART", [])
        if not uid_rows or not start_rows:
            props = {}
            return
        uid = uid_rows[0][1]
        start_params, start_value = start_rows[0]
        starts_at = _parse_datetime(start_value, start_params)
        end_rows = props.get("DTEND", [])
        duration_rows = props.get("DURATION", [])
        if end_rows:
            end_params, end_value = end_rows[0]
            if re.fullmatch(r"\d{8}", end_value):
                ends_at = datetime.strptime(end_value, "%Y%m%d").replace(tzinfo=MSK)
            else:
                ends_at = _parse_datetime(end_value, end_params)
        elif duration_rows:
            ends_at = starts_at + _parse_duration(duration_rows[0][1])
        elif re.fullmatch(r"\d{8}", start_value):
            ends_at = starts_at + timedelta(days=1)
        else:
            ends_at = starts_at + timedelta(hours=1)
        status = (props.get("STATUS", [[{}, ""]])[0][1] or "").upper()
        transp = (props.get("TRANSP", [[{}, ""]])[0][1] or "").upper()
        events.append(
            IcalEvent(
                uid=uid,
                starts_at=starts_at,
                ends_at=ends_at,
                cancelled=status == "CANCELLED",
                transparent=transp == "TRANSPARENT",
            )
        )
        props = {}

    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            props = {}
            continue
        if line == "END:VEVENT":
            if in_event:
                flush()
            in_event = False
            continue
        if not in_event:
            continue
        name, params, value = _split_property(line)
        props.setdefault(name, []).append((params, value))
    return events


async def fetch_ical(url: str) -> str:
    async with httpx.AsyncClient(timeout=ICAL_FETCH_TIMEOUT, follow_redirects=True) as client:
        res = await client.get(url)
        res.raise_for_status()
        body = res.content
        if len(body) > MAX_ICAL_BYTES:
            raise ValueError("iCal слишком большой")
        return body.decode("utf-8", errors="replace")
