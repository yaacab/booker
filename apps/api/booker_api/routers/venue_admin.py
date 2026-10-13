"""Administrative venue catalog lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import (
    User,
    Venue,
    VenueImportBatch,
    VenuePhoto,
    VenueSource,
    VenueStatusHistory,
    VenueTariff,
)
from booker_api.schemas import VenueModerationIn, VenueStatusIn
from booker_api.security import audit, require_admin
from booker_api.venue_catalog import (
    MODERATION_STATUSES,
    change_partnership_status,
    update_freshness,
)

router = APIRouter(prefix="/admin/venue-catalog", tags=["admin", "venue-catalog"])


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _item(db: Session, venue: Venue) -> dict:
    sources = db.query(VenueSource).filter(VenueSource.venue_id == venue.id).count()
    return {
        "id": venue.id,
        "name": venue.name,
        "address": venue.address,
        "source_type": venue.source_type,
        "source_attribution": venue.source_attribution,
        "partnership_status": venue.partnership_status,
        "is_claimed": venue.is_claimed,
        "is_partner": venue.is_partner,
        "moderation_status": venue.moderation_status,
        "completeness_score": venue.completeness_score,
        "data_freshness_status": venue.data_freshness_status,
        "last_verified_at": _iso(venue.last_verified_at),
        "last_crawled_at": _iso(venue.last_crawled_at),
        "source_count": sources,
    }


@router.get("/venues")
def list_venues(
    partnership_status: str | None = None,
    moderation_status: str | None = None,
    source_type: str | None = None,
    limit: int = 200,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Venue)
    if partnership_status:
        query = query.filter(Venue.partnership_status == partnership_status)
    if moderation_status:
        query = query.filter(Venue.moderation_status == moderation_status)
    if source_type:
        query = query.filter(Venue.source_type == source_type)
    rows = query.order_by(Venue.name).limit(min(max(limit, 1), 1000)).all()
    return {"items": [_item(db, row) for row in rows]}


@router.get("/venues/{venue_id}/history")
def venue_history(
    venue_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(Venue, venue_id):
        raise HTTPException(404, "Площадка не найдена")
    rows = (
        db.query(VenueStatusHistory)
        .filter(VenueStatusHistory.venue_id == venue_id)
        .order_by(VenueStatusHistory.changed_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "old_status": row.old_status,
                "new_status": row.new_status,
                "changed_by": row.changed_by,
                "changed_at": _iso(row.changed_at),
                "comment": row.comment,
            }
            for row in rows
        ]
    }


@router.post("/venues/{venue_id}/status")
def set_venue_status(
    venue_id: str,
    body: VenueStatusIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    try:
        change_partnership_status(
            db,
            venue,
            body.partnership_status,
            changed_by=user.id,
            comment=body.comment,
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    audit(
        db,
        actor_user_id=user.id,
        action="venue.partnership_status_changed",
        entity_type="venue",
        entity_id=venue.id,
        payload={"partnership_status": body.partnership_status, "comment": body.comment},
    )
    db.commit()
    db.refresh(venue)
    return _item(db, venue)


@router.post("/venues/{venue_id}/moderation")
def set_venue_moderation(
    venue_id: str,
    body: VenueModerationIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Площадка не найдена")
    if body.moderation_status not in MODERATION_STATUSES:
        raise HTTPException(400, "Недопустимый статус модерации")
    old_status = venue.moderation_status
    venue.moderation_status = body.moderation_status
    update_freshness(venue)
    audit(
        db,
        actor_user_id=user.id,
        action="venue.moderation_status_changed",
        entity_type="venue",
        entity_id=venue.id,
        payload={
            "old_status": old_status,
            "new_status": body.moderation_status,
            "comment": body.comment,
        },
    )
    db.commit()
    db.refresh(venue)
    return _item(db, venue)


@router.post("/freshness/recalculate")
def recalculate_freshness(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    counts = {"fresh": 0, "aging": 0, "stale": 0, "needs_review": 0}
    for venue in db.query(Venue).all():
        counts[update_freshness(venue)] += 1
    db.commit()
    return counts


@router.get("/batches")
def list_batches(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(VenueImportBatch).order_by(VenueImportBatch.started_at.desc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "sequence_number": row.sequence_number,
                "city": row.city,
                "category": row.category,
                "administrative_district": row.administrative_district,
                "status": row.status,
                "found": row.found_count,
                "new": row.new_count,
                "duplicates": row.duplicate_count,
                "published": row.published_count,
                "needs_review": row.needs_review_count,
                "with_contacts": row.with_contacts_count,
                "with_prices": row.with_prices_count,
                "with_photos": row.with_photos_count,
                "with_official_website": row.with_official_website_count,
                "started_at": _iso(row.started_at),
                "completed_at": _iso(row.completed_at),
                "notes": row.notes,
            }
            for row in rows
        ]
    }


@router.get("/report")
def catalog_report(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total = db.query(Venue).count()

    def count(field, value):
        return db.query(Venue).filter(field == value).count()

    return {
        "total": total,
        "automated": count(Venue.source_type, "automated_import"),
        "unverified": count(Venue.partnership_status, "unverified_listing"),
        "claimed": count(Venue.partnership_status, "claimed"),
        "verified": count(Venue.partnership_status, "verified"),
        "partners": count(Venue.partnership_status, "partner"),
        "published": count(Venue.moderation_status, "published"),
        "needs_review": count(Venue.moderation_status, "needs_review"),
        "with_contacts": db.query(Venue).filter((Venue.phone != "") | (Venue.email != "")).count(),
        "with_prices": db.query(VenueTariff.venue_id).distinct().count(),
        "with_photos": db.query(VenuePhoto.venue_id).distinct().count(),
        "with_official_website": db.query(Venue).filter(Venue.official_website != "").count(),
        "with_sources": db.query(VenueSource.venue_id).distinct().count(),
    }
