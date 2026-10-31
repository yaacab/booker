"""Отзывы только после Completed (E20 / W4-REVIEW)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Artist, Booking, Review, User, Venue
from booker_api.publication_eligibility import target_is_public
from booker_api.routers.deals import _booking_participant_orgs
from booker_api.security import audit, current_user, membership

router = APIRouter(tags=["reviews"])


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: str = ""


def _writer_membership_ok(db: Session, user: User, org_id: str) -> bool:
    member = membership(db, user.id, org_id)
    return bool(member and member.role in {"owner", "admin", "manager"})


def _booking_parties(db: Session, booking: Booking) -> tuple[str, str]:
    """Return (customer_org_id, supplier_org_id)."""
    return _booking_participant_orgs(db, booking)


def _review_out(row: Review, *, public: bool = False) -> dict:
    result = {
        "id": row.id,
        "org_id": row.org_id,
        "rating": row.rating,
        "text": row.text,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if not public:
        result["booking_id"] = row.booking_id
        result["author_user_id"] = row.author_user_id
    return result


def _list_for_org(db: Session, org_id: str) -> dict:
    rows = (
        db.query(Review)
        .filter(Review.org_id == org_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return {"items": [_review_out(r, public=True) for r in rows]}


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
    is_customer = _writer_membership_ok(db, user, cust_org)
    is_supplier = _writer_membership_ok(db, user, sup_org)
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
def list_org_reviews(org_id: str, db: Session = Depends(get_db)):
    return _list_for_org(db, org_id)


@router.get("/artists/{artist_id}/reviews")
def list_artist_reviews(artist_id: str, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if not artist or not target_is_public(db, "artist", artist_id):
        raise HTTPException(404, "Артист не найден")
    return _list_for_org(db, artist.organization_id)


@router.get("/venues/{venue_id}/reviews")
def list_venue_reviews(venue_id: str, db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if not venue or not target_is_public(db, "venue", venue_id):
        raise HTTPException(404, "Площадка не найдена")
    return _list_for_org(db, venue.organization_id)
