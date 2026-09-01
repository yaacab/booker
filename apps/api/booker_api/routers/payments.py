import json

from fastapi import APIRouter, Depends, HTTPException, Request
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
from booker_api.payments.adapter import PaymentAdapterError, get_payment_adapter
from booker_api.rate_limit import client_key, webhook_limiter
from booker_api.routers.deals import _transition
from booker_api.schemas import PaymentIn, SignIn, WebhookIn
from booker_api.security import audit, current_user

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


@router.post("/bookings/{booking_id}/payments")
def create_payment(
    booking_id: str,
    body: PaymentIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    adapter = get_payment_adapter()
    try:
        idempotency_key = adapter.normalize_idempotency_key(body.idempotency_key)
    except PaymentAdapterError as exc:
        raise HTTPException(400, str(exc)) from exc
    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "idempotent": True}
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    if booking.status != "AwaitingPayment":
        raise HTTPException(409, "Оплата доступна после подписания договора")
    offer = db.get(Offer, booking.offer_id)
    version = db.get(OfferVersion, offer.active_version_id)
    pay = Payment(
        booking_id=booking.id,
        amount_rub=version.total_rub,
        status="pending",
        provider=adapter.name,
        idempotency_key=idempotency_key,
    )
    db.add(pay)
    db.flush()
    session = adapter.create_session(
        payment_id=pay.id,
        amount_rub=pay.amount_rub,
        idempotency_key=idempotency_key,
        booking_id=booking.id,
    )
    pay.status = session.status
    audit(
        db,
        actor_user_id=user.id,
        action="payment.created",
        entity_type="payment",
        entity_id=pay.id,
        payload={"amount_rub": pay.amount_rub, "provider": session.provider},
    )
    db.commit()
    db.refresh(pay)
    return {"id": pay.id, "status": pay.status, "amount_rub": pay.amount_rub}


def _apply_payment_webhook(body: WebhookIn, db: Session) -> dict:
    adapter = get_payment_adapter()
    try:
        event = adapter.verify_webhook(
            event_id=body.event_id,
            payment_id=body.payment_id,
            status=body.status,
            signature=body.signature,
        )
    except PaymentAdapterError as exc:
        raise HTTPException(401 if "подпись" in str(exc).lower() else 400, str(exc)) from exc
    seen = db.get(PaymentWebhookEvent, event.event_id)
    if seen:
        return json.loads(seen.response_json)
    payment = db.get(Payment, event.payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    booking = db.get(Booking, payment.booking_id)
    if event.status == "succeeded":
        payment.status = "succeeded"
        adapter.ledger.on_capture(payment.id, payment.amount_rub)
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
    elif event.status == "failed":
        payment.status = "failed"
        if booking.status != "Confirmed":
            pass
    response = {
        "ok": True,
        "payment_id": payment.id,
        "payment_status": payment.status,
        "booking_status": booking.status,
    }
    db.add(
        PaymentWebhookEvent(
            event_id=event.event_id,
            payment_id=payment.id,
            status=event.status,
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


@router.post("/payments/webhook")
def payment_webhook(body: WebhookIn, request: Request, db: Session = Depends(get_db)):
    webhook_limiter.check(client_key(request, "webhook"))
    return _apply_payment_webhook(body, db)


@router.post("/payments/{payment_id}/stub-complete")
def stub_complete(
    payment_id: str,
    body: dict,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if settings.payment_provider.strip().lower() not in {"", "stub"}:
        raise HTTPException(403, "Только stub-провайдер")
    status = body.get("status") or "succeeded"
    import hashlib
    import hmac

    event_id = f"stub-{payment_id}-{status}"
    payload = f"{event_id}:{payment_id}:{status}"
    signature = hmac.new(
        settings.webhook_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return _apply_payment_webhook(
        WebhookIn(event_id=event_id, payment_id=payment_id, status=status, signature=signature),
        db,
    )
