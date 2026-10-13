"""Owner-facing explanation of the public supply gate."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.models import Artist, Organization, Venue
from booker_api.publication_eligibility import (
    artist_publication_eligibility,
    venue_publication_eligibility,
)

LABELS = {
    "publication_enabled": "Публичная карточка включена владельцем",
    "verified": "Верификация одобрена",
    "moderation": "Публикация одобрена модератором",
    "claimed": "Площадка подтверждена представителем",
    "tariff": "Есть тариф с ценой",
    "media": "Есть медиа с подтверждёнными правами",
    "representative": "Назначен представитель owner или admin",
    "halls": "Есть зал",
    "calendar_30d": "Календарь подтверждён минимум на 30 дней",
    "calendar_entries": "В календаре есть актуальные записи",
}


def supply_completeness(db: Session, org: Organization) -> dict:
    if org.kind not in {"artist", "venue"}:
        return {"score": 100, "items": [], "applicable": False, "eligible": False}

    if org.kind == "artist":
        profile = db.query(Artist).filter(Artist.organization_id == org.id).first()
        eligibility = artist_publication_eligibility(db, profile) if profile else None
    else:
        profile = db.query(Venue).filter(Venue.organization_id == org.id).first()
        eligibility = venue_publication_eligibility(db, profile) if profile else None

    items = [
        {
            "id": "catalog_profile",
            "label": "Создан профиль поставщика",
            "done": profile is not None,
        }
    ]
    if eligibility:
        items.extend(
            {"id": code, "label": LABELS[code], "done": passed}
            for code, passed in eligibility.checks.items()
        )
    else:
        required = [
            "publication_enabled",
            "verified",
            "tariff",
            "media",
            "representative",
            "calendar_30d",
            "calendar_entries",
        ]
        if org.kind == "venue":
            required.extend(("moderation", "claimed", "halls"))
        items.extend(
            {"id": code, "label": LABELS[code], "done": False} for code in required
        )

    done_count = sum(1 for item in items if item["done"])
    score = round(100 * done_count / len(items)) if items else 0
    return {
        "score": score,
        "items": items,
        "applicable": True,
        "eligible": bool(eligibility and eligibility.eligible),
        "reason_codes": eligibility.reason_codes if eligibility else [item["id"] for item in items],
    }
