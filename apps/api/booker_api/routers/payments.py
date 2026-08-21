import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import (
    AvailabilitySlot,
    Booking,
    Contract,
    Conversation,
    Message,
    Offer,
    OfferVersion,
    Payment,
    PaymentWebhookEvent,
    User,
)
from booker_api.routers.deals import _transition
from booker_api.schemas import PaymentIn, SignIn, WebhookIn
from booker_api.security import audit, current_user, verify_webhook_signature

router = APIRouter(tags=["payments"])

CONTRACT_TEMPLATE = """Черновик прямого договора сторон (не КЭП, не сила до утверждения юристом).
Букер — агрегатор цифровых услуг: https://bukergo.ru/legal/offer
Букер не артист, не арендодатель, не банк и не страховщик.
Стороны: заказчик и организация исполнителя/площадки. Каждая бронь — отдельная сделка.
Цена только с сервера. Прямая оплата вне платформы снимает сопровождение.
Спор — оператор, не ИИ. Категории: https://bukergo.ru/legal/disputes
Гонорар: {honorarium} ₽, комиссия платформы: {commission} ₽, итого: {total} ₽.
quote_id={quote_id}
Редакция юридического пакета: 2026-08-18-draft
"""


@router.post("/bookings/{booking_id}/contract")
def create_contract(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    if booking.status not in {"DateHeld", "AwaitingContract"}:
        raise HTTPException(409, "Сначала удержите дату")
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id)
    existing = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    if existing:
        return {"id": existing.id, "status": booking.status}
    body = CONTRACT_TEMPLATE.format(
        honorarium=version.honorarium_rub,
        commission=version.commission_rub,
        total=version.total_rub,
        quote_id=version.id,
    )
    contract = Contract(
        booking_id=booking.id,
        body=body,
        otp_customer="123456",
        otp_supplier="123456",
    )
    db.add(contract)
    db.flush()
    _transition(booking, "AwaitingContract")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    db.add(Message(conversation_id=conv.id, kind="system", body="Договор готов к подписи OTP."))
    audit(
        db,
        actor_user_id=user.id,
        action="contract.created",
        entity_type="contract",
        entity_id=contract.id,
    )
    db.commit()
    db.refresh(contract)
    return {"id": contract.id, "body": contract.body, "status": booking.status}


@router.post("/contracts/{contract_id}/sign")
def sign_contract(
    contract_id: str,
    body: SignIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Договор не найден")
    expected = contract.otp_customer if body.side == "customer" else contract.otp_supplier
    if body.otp != expected:
        raise HTTPException(403, "Неверный OTP")
    if body.side == "customer":
        contract.customer_signed = True
    elif body.side == "supplier":
        contract.supplier_signed = True
    else:
        raise HTTPException(400, "side: customer|supplier")
    booking = db.get(Booking, contract.booking_id)
    if contract.customer_signed and contract.supplier_signed and booking.status == "AwaitingContract":
        _transition(booking, "AwaitingPayment")
        conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
        db.add(Message(conversation_id=conv.id, kind="system", body="Договор подписан. Ожидается предоплата."))
    audit(
        db,
        actor_user_id=user.id,
        action="contract.signed",
        entity_type="contract",
        entity_id=contract.id,
        payload={"side": body.side},
    )
    db.commit()
    return {
        "customer_signed": contract.customer_signed,
        "supplier_signed": contract.supplier_signed,
        "booking_status": booking.status,
    }


class StubProvider:
    name = "stub"

    def charge(self, payment: Payment) -> dict:
        return {"provider": self.name, "payment_id": payment.id, "status": "pending"}


def provider():
    if settings.payment_provider != "stub":
        raise HTTPException(501, "Боевой платёжный партнёр за фичефлагом, сейчас только stub")
    return StubProvider()


@router.post("/bookings/{booking_id}/payments")
def create_payment(
    booking_id: str,
    body: PaymentIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    existing = db.query(Payment).filter(Payment.idempotency_key == body.idempotency_key).one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "idempotent": True}
    if booking.status != "AwaitingPayment":
        raise HTTPException(409, "Оплата доступна после подписания договора")
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id)
    pay = Payment(
        booking_id=booking.id,
        amount_rub=version.total_rub,
        status="pending",
        provider=provider().name,
        idempotency_key=body.idempotency_key,
    )
    db.add(pay)
    db.flush()
    provider().charge(pay)
    audit(
        db,
        actor_user_id=user.id,
        action="payment.created",
        entity_type="payment",
        entity_id=pay.id,
        payload={"amount_rub": pay.amount_rub},
    )
    db.commit()
    db.refresh(pay)
    return {"id": pay.id, "status": pay.status, "amount_rub": pay.amount_rub}


@router.post("/payments/webhook")
def payment_webhook(body: WebhookIn, db: Session = Depends(get_db)):
    payload = f"{body.event_id}:{body.payment_id}:{body.status}"
    if not verify_webhook_signature(payload, body.signature):
        raise HTTPException(401, "Неверная подпись webhook")
    seen = db.get(PaymentWebhookEvent, body.event_id)
    if seen:
        return json.loads(seen.response_json)
    payment = db.get(Payment, body.payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    booking = db.get(Booking, payment.booking_id)
    if body.status == "succeeded":
        payment.status = "succeeded"
        if booking.status == "AwaitingPayment":
            _transition(booking, "Confirmed")
            slot = db.get(AvailabilitySlot, booking.slot_id)
            slot.status = "confirmed"
            conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
            db.add(
                Message(
                    conversation_id=conv.id,
                    kind="system",
                    body="Предоплата получена. Бронирование подтверждено.",
                )
            )
    elif body.status == "failed":
        payment.status = "failed"
        if booking.status != "Confirmed":
            pass
    else:
        raise HTTPException(400, "status: succeeded|failed")
    response = {
        "ok": True,
        "payment_id": payment.id,
        "payment_status": payment.status,
        "booking_status": booking.status,
    }
    db.add(
        PaymentWebhookEvent(
            event_id=body.event_id,
            payment_id=payment.id,
            status=body.status,
            response_json=json.dumps(response),
        )
    )
    audit(
        db,
        actor_user_id=None,
        action="payment.webhook",
        entity_type="payment",
        entity_id=payment.id,
        payload=response,
    )
    db.commit()
    return response


@router.post("/payments/{payment_id}/stub-complete")
def stub_complete(
    payment_id: str,
    body: dict,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if settings.payment_provider != "stub":
        raise HTTPException(403, "Только stub-провайдер")
    status = body.get("status") or "succeeded"
    import hashlib
    import hmac

    event_id = f"stub-{payment_id}-{status}"
    payload = f"{event_id}:{payment_id}:{status}"
    signature = hmac.new(
        settings.webhook_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return payment_webhook(
        WebhookIn(event_id=event_id, payment_id=payment_id, status=status, signature=signature),
        db,
    )
