"""Minimal iCalendar (RFC 5545) parser for busy-time import."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from booker_api.security import aware

MSK = ZoneInfo("Europe/Moscow")
MAX_ICAL_BYTES = 512_000
ICAL_FETCH_TIMEOUT = 10.0
ICAL_MAX_REDIRECTS = 5

# Extra reserved / special-use nets beyond ipaddress "is_*" helpers.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("2001:db8::/32"),
)


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


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    return any(ip in net for net in _BLOCKED_NETWORKS)


def validate_ical_fetch_url(url: str) -> None:
    """HTTPS-only fetch target; reject private/loopback/link-local/metadata/reserved IPs.

    Re-run on every redirect hop. DNS is resolved here so literal and hostname
    targets that point at internal addresses fail closed before the request.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("iCal URL должен быть https://")
    host = parsed.hostname
    if not host:
        raise ValueError("Некорректный iCal URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("iCal URL не должен содержать credentials")
    if parsed.port is not None and parsed.port not in (443,):
        raise ValueError("iCal URL: разрешён только порт 443")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise ValueError("iCal URL указывает на недоступный/приватный адрес")
        return

    port = parsed.port or 443
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Не удалось разрешить хост iCal") from exc
    if not infos:
        raise ValueError("Не удалось разрешить хост iCal")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked_ip(ip):
            raise ValueError("iCal URL указывает на недоступный/приватный адрес")


async def fetch_ical(url: str) -> str:
    current = url.strip()
    async with httpx.AsyncClient(timeout=ICAL_FETCH_TIMEOUT, follow_redirects=False) as client:
        for _ in range(ICAL_MAX_REDIRECTS + 1):
            validate_ical_fetch_url(current)
            res = await client.get(current)
            if res.is_redirect:
                location = res.headers.get("location")
                if not location:
                    raise ValueError("iCal редирект без Location")
                current = urljoin(str(res.url), location)
                continue
            res.raise_for_status()
            body = res.content
            if len(body) > MAX_ICAL_BYTES:
                raise ValueError("iCal слишком большой")
            return body.decode("utf-8", errors="replace")
    raise ValueError("Слишком много редиректов iCal")
