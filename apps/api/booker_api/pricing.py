from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import Booking, Event

_ACTIVE = (
    "Negotiation",
    "DateHeld",
    "AwaitingContract",
    "AwaitingPayment",
    "Confirmed",
    "InProgress",
    "Completed",
    "Dispute",
    "Resolved",
)


def first_deal_waive(db: Session, customer_org_id: str, *, exclude_booking_id: str | None = None) -> bool:
    """Первая сделка заказчика в контуре — комиссия платформы 0. Гонорар не трогаем."""
    q = (
        db.query(Booking)
        .join(Event, Event.id == Booking.event_id)
        .filter(Event.organization_id == customer_org_id, Booking.status.in_(_ACTIVE))
    )
    if exclude_booking_id:
        q = q.filter(Booking.id != exclude_booking_id)
    return q.count() == 0


def price_breakdown(honorarium_rub: int, *, waive_commission: bool = False) -> dict:
    if waive_commission:
        return {
            "honorarium_rub": honorarium_rub,
            "commission_rate": 0.0,
            "commission_rub": 0,
            "total_rub": honorarium_rub,
            "currency": "RUB",
            "source": "Первая сделка: комиссия платформы 0. Гонорар как есть.",
        }
    rate = settings.pilot_commission_rate
    commission = round(honorarium_rub * rate)
    return {
        "honorarium_rub": honorarium_rub,
        "commission_rate": rate,
        "commission_rub": commission,
        "total_rub": honorarium_rub + commission,
        "currency": "RUB",
    }
