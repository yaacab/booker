from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from booker_api.models import MoneyMovement, Payment


def append_money_movement(
    db: Session,
    *,
    payment: Payment,
    kind: str,
    direction: str,
    amount_rub: int,
    source_type: str,
    source_id: str,
    actor_user_id: str | None = None,
    metadata: dict | None = None,
) -> MoneyMovement:
    """Append one idempotent movement; corrections must use a compensating row."""
    if amount_rub <= 0:
        raise ValueError("Сумма движения должна быть положительной")
    if direction not in {"credit", "debit"}:
        raise ValueError("Неизвестное направление движения")
    existing = (
        db.query(MoneyMovement)
        .filter_by(source_type=source_type, source_id=source_id, kind=kind)
        .one_or_none()
    )
    expected = {
        "payment_id": payment.id,
        "booking_id": payment.booking_id,
        "obligation_id": payment.obligation_id,
        "direction": direction,
        "amount_rub": amount_rub,
        "provider": payment.provider,
    }
    if existing:
        if any(getattr(existing, key) != value for key, value in expected.items()):
            raise ValueError("Источник денежного движения уже использован с другими данными")
        return existing
    if direction == "debit":
        credited = (
            db.query(func.coalesce(func.sum(MoneyMovement.amount_rub), 0))
            .filter_by(payment_id=payment.id, direction="credit")
            .scalar()
        )
        debited = (
            db.query(func.coalesce(func.sum(MoneyMovement.amount_rub), 0))
            .filter_by(payment_id=payment.id, direction="debit")
            .scalar()
        )
        if amount_rub > credited - debited:
            raise ValueError("Дебет превышает доступную захваченную сумму")
    movement = MoneyMovement(
        booking_id=payment.booking_id,
        payment_id=payment.id,
        obligation_id=payment.obligation_id,
        kind=kind,
        direction=direction,
        amount_rub=amount_rub,
        currency="RUB",
        provider=payment.provider,
        source_type=source_type,
        source_id=source_id,
        actor_user_id=actor_user_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
    )
    db.add(movement)
    return movement
