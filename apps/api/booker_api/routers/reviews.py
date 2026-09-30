"""Отзывы только после Completed (E20 / W4-REVIEW)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, Booking, Event, Offer, Request, Review, User, Venue, VenueHall
from booker_api.routers.catalog import _optional_user
from booker_api.security import audit, current_user, membership
from booker_api.venue_catalog import is_publicly_listed

router = APIRouter(tags=["reviews"])


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: str = ""


def _membership_ok(db: Session, user: User, org_id: str) -> bool:
    return bool(membership(db, user.id, org_id) or user.is_platform_admin)


def _booking_parties(db: Session, booking: Booking) -> tuple[str, str]:
    """Return (customer_org_id, supplier_org_id)."""
    offer = db.get(Offer, booking.offer_id)
    if not offer:
        raise HTTPException(404, "Бронь не найдена")
    req = db.get(Request, offer.request_id)
    event = db.get(Event, booking.event_id)
    if not req or not event:
        raise HTTPException(404, "Бронь не найдена")
    return event.organization_id, req.supplier_org_id


def _review_out(row: Review) -> dict:
    return {
        "id": row.id,
        "booking_id": row.booking_id,
        "author_user_id": row.author_user_id,
        "org_id": row.org_id,
        "rating": row.rating,
        "text": row.text,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _list_for_org(db: Session, org_id: str, *, include_private: bool = False) -> dict:
    rows = (
        db.query(Review, Request.resource_type, Request.resource_id)
        .join(Booking, Booking.id == Review.booking_id)
        .join(Offer, Offer.id == Booking.offer_id)
        .join(Request, Request.id == Offer.request_id)
        .filter(Review.org_id == org_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    visible = []
    for review, resource_type, resource_id in rows:
        if resource_type in {"venue", "hall"} and not include_private:
            if resource_type == "hall":
                hall = db.get(VenueHall, resource_id)
                resource_id = hall.venue_id if hall else None
            venue = db.get(Venue, resource_id) if resource_id else None
            if not venue or not is_publicly_listed(db, venue):
                continue
        visible.append(_review_out(review))
    return {"items": visible}


@router.post("/bookings/{booking_id}/reviews")
def create_review(
    booking_id: str,
    body: ReviewIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")

    cust_org, sup_org = _booking_parties(db, booking)
    is_customer = _membership_ok(db, user, cust_org)
    is_supplier = _membership_ok(db, user, sup_org)
    if not (is_customer or is_supplier):
        raise HTTPException(403, "Нет доступа")

    if cust_org == sup_org:
        raise HTTPException(403, "Нельзя оставить отзыв о своей организации")

    if booking.status != "Completed":
        raise HTTPException(409, "Отзыв доступен только после завершения сделки")

    # Отзыв о контрагенте, не о своей стороне
    if is_customer and not is_supplier:
        target_org = sup_org
    elif is_supplier and not is_customer:
        target_org = cust_org
    else:
        # Участник обеих орг (редко) — явно запрещаем самооценку
        raise HTTPException(403, "Нельзя оставить отзыв о своей организации")

    existing = (
        db.query(Review)
        .filter(Review.booking_id == booking.id, Review.author_user_id == user.id)
        .one_or_none()
    )
    if existing:
        raise HTTPException(409, "Отзыв по этой брони уже оставлен")

    text = (body.text or "").strip()
    row = Review(
        booking_id=booking.id,
        author_user_id=user.id,
        org_id=target_org,
        rating=body.rating,
        text=text,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Отзыв по этой брони уже оставлен") from exc

    audit(
        db,
        actor_user_id=user.id,
        action="review.created",
        entity_type="review",
        entity_id=row.id,
        payload={"booking_id": booking.id, "org_id": target_org, "rating": body.rating},
    )
    db.commit()
    db.refresh(row)
    return _review_out(row)


@router.get("/organizations/{org_id}/reviews")
def list_org_reviews(
    org_id: str,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    include_private = bool(user and _membership_ok(db, user, org_id))
    return _list_for_org(db, org_id, include_private=include_private)


def profile_reviews(db: Session, target_type: str, target_id: str, org_id: str) -> dict:
    profile_filter = and_(Request.resource_type == target_type, Request.resource_id == target_id)
    if target_type == "venue":
        halls = db.query(VenueHall.id).filter_by(venue_id=target_id)
        profile_filter = or_(profile_filter, and_(Request.resource_type == "hall", Request.resource_id.in_(halls)))
    query = db.query(Review).join(Booking, Booking.id == Review.booking_id).join(
        Offer, Offer.id == Booking.offer_id
    ).join(Request, Request.id == Offer.request_id).filter(
        Review.org_id == org_id, Booking.status == "Completed", profile_filter
    )
    count, average = query.with_entities(func.count(Review.id), func.avg(Review.rating)).one()
    rows = query.order_by(Review.created_at.desc()).limit(100).all()
    return {"items": [{"id": r.id, "rating": r.rating, "text": r.text,
                       "created_at": r.created_at.isoformat()} for r in rows],
            "count": count, "average_rating": round(float(average), 1) if count >= 5 else None,
            "note": "Отзывы о конкретном профиле после завершённых сделок"}


@router.get("/artists/{artist_id}/reviews")
def list_artist_reviews(artist_id: str, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Артист не найден")
    return profile_reviews(db, "artist", artist.id, artist.organization_id)


@router.get("/venues/{venue_id}/reviews")
def list_venue_reviews(
    venue_id: str,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if not venue or (
        not is_publicly_listed(db, venue)
        and not (user and _membership_ok(db, user, venue.organization_id))
    ):
        raise HTTPException(404, "Площадка не найдена")
    return profile_reviews(db, "venue", venue.id, venue.organization_id)
