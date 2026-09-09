"""Venue catalog provenance, quality, freshness and duplicate rules."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from booker_api.models import Venue, VenuePhoto, VenueSource, VenueStatusHistory

PARTNERSHIP_STATUSES = frozenset({"unverified_listing", "claimed", "verified", "partner"})
MODERATION_STATUSES = frozenset({"published", "needs_review", "rejected", "archived"})
PUBLICATION_THRESHOLD = 55


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold().replace("ё", "е")
    return " ".join(re.findall(r"[a-zа-я0-9]+", text))


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return "7" + digits[1:] if len(digits) == 11 and digits[0] in "78" else digits


def website_domain(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else "https://" + value)
    return (parsed.hostname or "").casefold().removeprefix("www.")


def coordinates(row: dict) -> tuple[float | None, float | None]:
    lat, lon = row.get("lat"), row.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    match = re.fullmatch(
        r"\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*",
        str(row.get("address") or ""),
    )
    return (float(match.group(1)), float(match.group(2))) if match else (None, None)


def _meaningful_address(value: str | None) -> bool:
    return bool(value and any(char.isalpha() for char in value))


def completeness_score(row: dict) -> int:
    score = 0
    score += 15 if str(row.get("name") or "").strip() else 0
    score += 15 if _meaningful_address(str(row.get("address") or "")) else 0
    score += 10 if row.get("source_url") or row.get("sources") else 0
    score += 10 if row.get("capacity") else 0
    score += 10 if row.get("tariff_from_rub") else 0
    description = str(row.get("description") or "").strip()
    if description and description != "Площадка из Wikidata (Москва)":
        score += 7
    score += 5 if str(row.get("district") or "").strip() else 0
    score += 5 if str(row.get("metro") or "").strip() else 0
    score += 8 if str(row.get("official_website") or "").strip() else 0
    score += 5 if row.get("phone") or row.get("email") else 0
    score += 5 if row.get("photos") else 0
    lat, lon = coordinates(row)
    score += 5 if lat is not None and lon is not None else 0
    return min(score, 100)


def moderation_status(row: dict) -> str:
    essentials = bool(
        row.get("name")
        and _meaningful_address(str(row.get("address") or ""))
        and (row.get("source_url") or row.get("sources"))
    )
    return (
        "published"
        if essentials and completeness_score(row) >= PUBLICATION_THRESHOLD
        else "needs_review"
    )


def apply_automated_metadata(
    venue: Venue,
    row: dict,
    *,
    is_new: bool,
    checked_at: datetime,
) -> None:
    venue.source_type = "automated_import"
    if is_new:
        venue.partnership_status = "unverified_listing"
        venue.is_claimed = False
        venue.is_partner = False
        venue.status_changed_at = checked_at
    venue.completeness_score = completeness_score(row)
    venue.moderation_status = moderation_status(row)
    venue.last_crawled_at = checked_at
    venue.data_freshness_status = (
        "fresh" if venue.moderation_status == "published" else "needs_review"
    )
    venue.venue_type = str(row.get("venue_type") or "")
    venue.administrative_district = str(row.get("administrative_district") or "")
    venue.phone = str(row.get("phone") or "")
    venue.email = str(row.get("email") or "")
    venue.official_website = str(row.get("official_website") or "")
    venue.latitude, venue.longitude = coordinates(row)
    details = {
        key: row.get(key)
        for key in (
            "alternative_name",
            "area_sqm",
            "capacity_banquet",
            "capacity_reception",
            "capacity_theatre",
            "minimum_spend_rub",
            "deposit_rub",
            "price_per_person_rub",
            "booking_terms",
            "own_catering_allowed",
            "own_alcohol_allowed",
            "corkage_fee",
            "cuisine",
            "parking",
            "has_stage",
            "has_sound",
            "has_light",
            "has_screen_projector",
            "has_dressing_rooms",
            "has_wifi",
            "accessible",
            "noise_restrictions",
            "latest_event_time",
            "social_links",
            "event_contact",
            "number_of_halls",
        )
        if row.get(key) is not None
    }
    venue.details_json = json.dumps(details, ensure_ascii=False)


def record_source(db: Session, venue: Venue, row: dict, checked_at: datetime) -> None:
    sources = list(row.get("sources") or [])
    source_url = str(row.get("source_url") or "").strip()
    if source_url:
        sources.insert(
            0,
            {
                "field_name": "name,address,description,capacity",
                "source_url": source_url,
                "source_kind": str(row.get("attribution") or "open_data"),
            },
        )
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("source_url") or "").strip()
        if not url:
            continue
        field_name = str(source.get("field_name") or "general").strip() or "general"
        source_kind = str(source.get("source_kind") or row.get("attribution") or "open_data")
        existing = (
            db.query(VenueSource)
            .filter(
                VenueSource.venue_id == venue.id,
                VenueSource.field_name == field_name,
                VenueSource.source_url == url,
            )
            .one_or_none()
        )
        if existing:
            existing.checked_at = checked_at
            existing.source_kind = source_kind
            continue
        db.add(
            VenueSource(
                venue_id=venue.id,
                field_name=field_name,
                source_url=url,
                source_kind=source_kind,
                checked_at=checked_at,
            )
        )


def record_photos(db: Session, venue: Venue, row: dict) -> None:
    allowed_rights = {"official_permission", "licensed", "unknown", "do_not_publish"}
    for order, photo in enumerate(row.get("photos") or []):
        photo_url = str(photo.get("photo_url") or "").strip()
        source_url = str(photo.get("photo_source_url") or "").strip()
        rights = str(photo.get("photo_rights_status") or "unknown")
        if not photo_url or not source_url:
            continue
        if rights not in allowed_rights:
            rights = "unknown"
        existing = (
            db.query(VenuePhoto)
            .filter(VenuePhoto.venue_id == venue.id, VenuePhoto.photo_url == photo_url)
            .one_or_none()
        )
        if existing:
            existing.photo_source_url = source_url
            existing.photo_rights_status = rights
            existing.sort_order = order
            continue
        db.add(
            VenuePhoto(
                venue_id=venue.id,
                photo_url=photo_url,
                photo_source_url=source_url,
                photo_rights_status=rights,
                sort_order=order,
            )
        )


def public_disclosure(venue: Venue) -> str | None:
    if venue.source_type == "automated_import" and venue.partnership_status == "unverified_listing":
        return "Информация из открытых источников"
    return None


def change_partnership_status(
    db: Session,
    venue: Venue,
    new_status: str,
    *,
    changed_by: str,
    comment: str = "",
) -> None:
    if new_status not in PARTNERSHIP_STATUSES:
        raise ValueError("Недопустимый статус сотрудничества")
    old_status = venue.partnership_status
    timestamp = datetime.now(timezone.utc)
    venue.partnership_status = new_status
    venue.is_claimed = new_status in {"claimed", "verified", "partner"}
    venue.is_partner = new_status == "partner"
    venue.verified = new_status in {"verified", "partner"}
    venue.verified_status = "approved" if venue.verified else "pending"
    venue.status_changed_at = timestamp
    if venue.verified and venue.verified_at is None:
        venue.verified_at = timestamp
        venue.verified_by = changed_by
        venue.last_verified_at = timestamp
    if new_status == "partner" and venue.partnership_started_at is None:
        venue.partnership_started_at = timestamp
    db.add(
        VenueStatusHistory(
            venue_id=venue.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            changed_at=timestamp,
            comment=comment,
        )
    )


def update_freshness(venue: Venue, *, at: datetime | None = None) -> str:
    if venue.moderation_status == "needs_review":
        venue.data_freshness_status = "needs_review"
        return venue.data_freshness_status
    checked = venue.last_verified_at or venue.last_crawled_at
    if checked is None:
        venue.data_freshness_status = "needs_review"
        return venue.data_freshness_status
    current = at or datetime.now(timezone.utc)
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    age = (current - checked).days
    venue.data_freshness_status = "fresh" if age <= 90 else "aging" if age <= 180 else "stale"
    return venue.data_freshness_status


def _distance_meters(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def duplicate_score(row: dict, venue: Venue) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    if normalize_text(str(row.get("name") or "")) == normalize_text(venue.name):
        score += 0.34
        reasons.append("exact_name")
    if normalize_text(str(row.get("address") or "")) == normalize_text(venue.address):
        score += 0.38
        reasons.append("exact_address")
    incoming_phone = normalize_phone(str(row.get("phone") or ""))
    if incoming_phone and incoming_phone == normalize_phone(venue.phone):
        score += 0.62
        reasons.append("exact_phone")
    incoming_domain = website_domain(
        str(row.get("official_website") or row.get("source_url") or "")
    )
    existing_domain = website_domain(venue.official_website or venue.source_url)
    if incoming_domain and incoming_domain == existing_domain:
        score += 0.55
        reasons.append("exact_domain")
    lat, lon = coordinates(row)
    if (
        lat is not None
        and lon is not None
        and venue.latitude is not None
        and venue.longitude is not None
    ):
        distance = _distance_meters(lat, lon, venue.latitude, venue.longitude)
        if distance <= 40:
            score += 0.42
            reasons.append("near_coordinates")
    return min(score, 1.0), reasons
