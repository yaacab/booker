"""Public reputation facts and deal-room review projection (CONTRACT: no stars before 10)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from booker_api.models import Booking, Organization, Review, User
from booker_api.security import membership

RATING_THRESHOLD = 10


def org_reputation(db: Session, org_id: str) -> dict:
    rows = db.query(Review.rating).filter(Review.org_id == org_id).all()
    count = len(rows)
    payload: dict = {
        "org_id": org_id,
        "review_count": count,
        "show_rating": count >= RATING_THRESHOLD,
        "note": (
            "После десяти отзывов покажем среднюю оценку. Пока — только факты."
            if count < RATING_THRESHOLD
            else "Средняя оценка по подтверждённым отзывам."
        ),
    }
    if count >= RATING_THRESHOLD and rows:
        average = sum(int(r[0]) for r in rows) / count
        payload["average_rating"] = round(average, 1)
    return payload


def _writer_ok(db: Session, user: User, org_id: str) -> bool:
    member = membership(db, user.id, org_id)
    return bool(member and member.role in {"owner", "admin", "manager"})


def deal_review_projection(
    db: Session,
    *,
    booking: Booking,
    user: User,
    customer_org_id: str,
    supplier_org_id: str,
    role: str,
) -> dict | None:
    if booking.status != "Completed":
        return None
    my_review = (
        db.query(Review)
        .filter(Review.booking_id == booking.id, Review.author_user_id == user.id)
        .one_or_none()
    )
    counterparty_org_id = supplier_org_id if role == "customer" else customer_org_id
    counterparty = db.get(Organization, counterparty_org_id)
    can_submit = (
        my_review is None
        and _writer_ok(db, user, customer_org_id if role == "customer" else supplier_org_id)
        and customer_org_id != supplier_org_id
    )
    peer_count = (
        db.query(func.count(Review.id)).filter(Review.booking_id == booking.id).scalar() or 0
    )
    return {
        "can_submit": can_submit,
        "my_review": None
        if my_review is None
        else {
            "id": my_review.id,
            "rating": my_review.rating,
            "text": my_review.text,
            "created_at": my_review.created_at.isoformat() if my_review.created_at else None,
        },
        "reviews_on_booking": int(peer_count),
        "pending_counterparty": peer_count < 2,
        "target_org_id": counterparty_org_id,
        "target_org_name": counterparty.name if counterparty else None,
    }
