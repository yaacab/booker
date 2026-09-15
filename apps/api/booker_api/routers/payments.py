import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from booker_api.commerce.promotions import attribute_booking
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import (
    AvailabilitySlot,
    Booking,
    BookingHold,
    Contract,
    Conversation,
    Event,
    Message,
    Offer,
    OfferVersion,
    Payment,
    PaymentWebhookEvent,
    User,
)
from booker_api.models import (
    Request as DealRequest,
)
from booker_api.notifications.service import notify, org_member_notifications
from booker_api.notifications.types import Channel
from booker_api.payments.adapter import (
    PaymentAdapterError,
    get_payment_adapter,
    payment_stub_enabled,
)
from booker_api.rate_limit import auth_limiter, client_key, upload_limiter, webhook_limiter
from booker_api.routers.deals import (
    _lock_booking_resources,
    _lock_event,
    _lock_open_event,
    _require_open_event,
    _transition,
    _validate_event_slot,
)
from booker_api.schemas import PaymentIn, SignIn, WebhookIn
from booker_api.security import (
    audit,
    aware,
    current_user,
    now,
    require_org_writer,
)

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


def _new_otp(exclude: str | None = None) -> str:
    code = f"{secrets.randbelow(900000) + 100000}"
    while exclude is not None and code == exclude:
        code = f"{secrets.randbelow(900000) + 100000}"
    return code


def _require_contract_reservation(db, booking, event, offer, req):
    _require_open_event(event)
    _lock_booking_resources(db, [booking])
    slot = db.execute(select(AvailabilitySlot).where(AvailabilitySlot.id == booking.slot_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    db.refresh(booking)
    hold = db.query(BookingHold).filter(BookingHold.booking_id == booking.id,
        BookingHold.slot_id == booking.slot_id, BookingHold.status == "active", BookingHold.expires_at > now()).first()
    other = db.query(BookingHold).filter(BookingHold.slot_id == booking.slot_id,
        BookingHold.booking_id != booking.id, BookingHold.status == "active").first()
    if not slot or not hold or other or slot.status != "held":
        raise HTTPException(409, "Резерв даты недействителен. Проверьте сделку перед подписанием")
    db.refresh(offer)
    version = db.get(OfferVersion, offer.active_version_id)
    if not version:
        raise HTTPException(409, "Условия предложения не найдены")
    db.refresh(version)
    if not (version.customer_ack and version.supplier_ack):
        raise HTTPException(409, "Условия не подтверждены обеими сторонами")
    _validate_event_slot(db, event, req, slot, own_hold=True)
    return version


@router.post("/bookings/{booking_id}/contract")
def create_contract(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = db.get(Event, booking.event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    upload_limiter.check(f"contract-create:{user.id}")
    _lock_open_event(db, event)
    db.refresh(booking)
    if booking.status not in {"DateHeld", "AwaitingContract"}:
        raise HTTPException(409, "Сначала удержите дату")
    offer = db.get(Offer, booking.offer_id)
    existing = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    if existing:
        return {
            "id": existing.id,
            "status": booking.status,
            "otp_delivered": True,
        }
    req = db.get(DealRequest, offer.request_id)
    version = _require_contract_reservation(db, booking, event, offer, req)
    otp_customer = _new_otp()
    otp_supplier = _new_otp(exclude=otp_customer)
    body = CONTRACT_TEMPLATE.format(
        honorarium=version.honorarium_rub,
        commission=version.commission_rub,
        total=version.total_rub,
        quote_id=version.id,
    )
    contract = Contract(
        booking_id=booking.id,
        body=body,
        otp_customer=otp_customer,
        otp_supplier=otp_supplier,
    )
    db.add(contract)
    db.flush()
    _transition(booking, "AwaitingContract")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    db.add(
        Message(
            conversation_id=conv.id,
            kind="system",
            body="Договор готов к подписи. Код OTP отправлен в уведомления сторон (не показывается в UI).",
        )
    )
    offer_req = db.get(DealRequest, offer.request_id) if offer else None
    customer_notes = org_member_notifications(
        db,
        organization_id=event.organization_id,
        template="contract.otp",
        subject="Код подписи договора (заказчик)",
        body=f"Ваш код подписи договора в Букере: {otp_customer}",
        entity_type="contract",
        entity_id=contract.id,
        channels=(Channel.IN_APP, Channel.EMAIL),
        roles=("owner", "admin", "manager"),
    )
    supplier_notes: list = []
    if offer_req and offer_req.supplier_org_id:
        supplier_notes = org_member_notifications(
            db,
            organization_id=offer_req.supplier_org_id,
            template="contract.otp",
            subject="Код подписи договора (исполнитель)",
            body=f"Ваш код подписи договора в Букере: {otp_supplier}",
            entity_type="contract",
            entity_id=contract.id,
            channels=(Channel.IN_APP, Channel.EMAIL),
            roles=("owner", "admin", "manager"),
        )
    notify(db, actor_user_id=user.id, notifications=customer_notes + supplier_notes)
    audit(
        db,
        actor_user_id=user.id,
        action="contract.created",
        entity_type="contract",
        entity_id=contract.id,
    )
    db.commit()
    db.refresh(contract)
    return {
        "id": contract.id,
        "body": contract.body,
        "status": booking.status,
        "otp_delivered": True,
    }


def _lock_contract_event(db, event):
    _lock_event(db, event)


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
    booking = db.get(Booking, contract.booking_id)
    offer = db.get(Offer, booking.offer_id)
    req = db.get(DealRequest, offer.request_id)
    event = db.get(Event, booking.event_id)
    if body.side == "customer":
        require_org_writer(db, user, event.organization_id)
    elif body.side == "supplier":
        require_org_writer(db, user, req.supplier_org_id)
    else:
        raise HTTPException(400, "side: customer|supplier")
    auth_limiter.check(f"contract-sign:{user.id}:{contract.id}")
    _lock_contract_event(db, event)
    db.refresh(booking)
    db.refresh(contract)
    expected = contract.otp_customer if body.side == "customer" else contract.otp_supplier
    if not expected or not hmac.compare_digest(body.otp.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(403, "Неверный OTP")
    if (contract.customer_signed if body.side == "customer" else contract.supplier_signed):
        return {"customer_signed": contract.customer_signed, "supplier_signed": contract.supplier_signed,
            "booking_status": booking.status}
    if booking.status != "AwaitingContract":
        raise HTTPException(409, "Подписание недоступно в текущем состоянии сделки")
    version = _require_contract_reservation(db, booking, event, offer, req)
    if f"quote_id={version.id}" not in [line.strip() for line in contract.body.splitlines()]:
        raise HTTPException(409, "Договор относится к другой версии условий. Обратитесь к оператору")
    if body.side == "customer":
        contract.customer_signed = True
    else:
        contract.supplier_signed = True
    if contract.customer_signed and contract.supplier_signed and booking.status == "AwaitingContract":
        _transition(booking, "AwaitingPayment")
        from booker_api.notifications.lifecycle import booking_notice
        booking_notice(db, booking, template='payment.required', subject='Следующий шаг — оплата сделки',
            body='Обе стороны подписали договор. Откройте сделку, проверьте срок резерва и условия оплаты. Уведомление не подтверждает списание денег.',
            key=contract.id, customer_only=True, actor_id=user.id)
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
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = db.get(Event, booking.event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    require_org_writer(db, user, event.organization_id)
    webhook_limiter.check(f"payment-create:{user.id}")
    adapter = get_payment_adapter()
    try:
        raw_key = adapter.normalize_idempotency_key(body.idempotency_key)
    except PaymentAdapterError as exc:
        raise HTTPException(400, str(exc)) from exc
    idempotency_key = hashlib.sha256(f"{booking.id}:{raw_key}".encode()).hexdigest()
    _lock_contract_event(db, event)
    # Serialize checkout for this booking, including SQLite where FOR UPDATE is ignored.
    db.execute(update(Booking).where(Booking.id == booking.id).values(status=Booking.status))
    db.refresh(booking)
    pay = db.query(Payment).filter(Payment.booking_id == booking.id).first()
    replay = pay is not None
    if pay and (pay.session_state == "ready" or pay.status != "pending"):
        return _checkout_receipt(db, pay, booking, event, replay=True)
    if pay and pay.provider != adapter.name:
        raise HTTPException(409, "Платёж ожидает сверки с исходным партнёром. Обратитесь к оператору")
    version = _checkout_reservation(db, booking, event)
    if not pay:
        pay = Payment(booking_id=booking.id, amount_rub=version.total_rub,
            status="pending", provider=adapter.name, idempotency_key=idempotency_key,
            session_state="creating")
        db.add(pay)
        db.flush()
        audit(db, actor_user_id=user.id, action="payment.created", entity_type="payment",
            entity_id=pay.id, payload={"amount_rub": pay.amount_rub, "provider": pay.provider})
        # Commit identity BEFORE an external request: a timeout/crash must not change
        # payment_id, amount or provider idempotency key on the next attempt.
        db.commit()
        _lock_contract_event(db, event)
        db.refresh(booking)
        db.refresh(pay)
        if pay.session_state == "ready" or pay.status != "pending":
            return _checkout_receipt(db, pay, booking, event, replay=True)
        version = _checkout_reservation(db, booking, event)
    if pay.amount_rub != version.total_rub:
        raise HTTPException(409, "Условия платежа требуют сверки. Обратитесь к оператору")
    try:
        session = adapter.create_session(payment_id=pay.id, amount_rub=pay.amount_rub,
            idempotency_key=pay.idempotency_key, booking_id=booking.id)
        _validate_checkout_session(session, pay)
    except (PaymentAdapterError, TimeoutError, ConnectionError):
        pay.session_state = "uncertain"
        audit(db, actor_user_id=user.id, action="payment.session_uncertain", entity_type="payment",
            entity_id=pay.id, payload={"provider": pay.provider})
        db.commit()
        raise HTTPException(502, "Партнёр не подтвердил создание счёта. Повторите запрос: сохранённый платёж будет использован снова") from None
    pay.checkout_url = session.checkout_url
    pay.provider_reference = session.provider_reference
    pay.session_state = "ready"
    # Creating checkout is never evidence of capture; only verified events record money.
    audit(db, actor_user_id=user.id, action="payment.session_ready", entity_type="payment",
        entity_id=pay.id, payload={"provider": pay.provider})
    db.commit()
    return _checkout_receipt(db, pay, booking, event, replay=replay)


def _checkout_reservation(db, booking, event):
    _require_open_event(event)
    if booking.status != "AwaitingPayment":
        raise HTTPException(409, "Оплата доступна после подписания договора")
    contract = db.query(Contract).filter_by(booking_id=booking.id).one_or_none()
    if not contract or not (contract.customer_signed and contract.supplier_signed):
        raise HTTPException(409, "Договор не подписан обеими сторонами")
    offer = db.get(Offer, booking.offer_id)
    req = db.get(DealRequest, offer.request_id)
    return _require_contract_reservation(db, booking, event, offer, req)


def _validate_checkout_session(session, pay):
    if session.payment_id != pay.id or session.provider != pay.provider or session.status != "pending":
        raise PaymentAdapterError("Некорректная сессия партнёра")
    if session.provider_reference is not None and (not session.provider_reference.strip() or len(session.provider_reference) > 255):
        raise PaymentAdapterError("Некорректный идентификатор партнёра")
    if session.checkout_url is not None:
        try:
            url = urlsplit(session.checkout_url)
        except ValueError:
            raise PaymentAdapterError("Некорректный адрес оплаты") from None
        if (len(session.checkout_url) > 4096 or url.scheme != "https" or not url.hostname
                or url.username or url.password or not session.provider_reference
                or any(ord(c) <= 32 for c in session.checkout_url)):
            raise PaymentAdapterError("Некорректный адрес оплаты")


def _checkout_receipt(db, pay, booking, event, *, replay):
    allowed = (booking.status == "AwaitingPayment" and event.status not in {"Cancelled", "Completed"}
        and pay.provider == settings.payment_provider.strip().lower())
    hold = db.query(BookingHold).filter_by(booking_id=booking.id, slot_id=booking.slot_id, status="active").first()
    slot = db.get(AvailabilitySlot, booking.slot_id)
    allowed = (allowed and hold is not None and aware(hold.expires_at) > now()
        and event.ends_at is not None and aware(event.event_date) > now()
        and slot is not None and slot.status == "held")
    return {"id": pay.id, "status": pay.status, "idempotent": replay,
        "amount_rub": pay.amount_rub, "provider": pay.provider,
        "session_state": pay.session_state,
        "checkout_url": pay.checkout_url if allowed and pay.status == "pending" and pay.session_state == "ready" else None}


def _lock_payment_context(db: Session, payment: Payment) -> Booking:
    booking = db.get(Booking, payment.booking_id)
    event = db.get(Event, booking.event_id) if booking else None
    if not event:
        raise HTTPException(404, "Бронь не найдена")
    _lock_contract_event(db, event)
    db.refresh(booking)
    _lock_booking_resources(db, [booking])
    db.execute(select(AvailabilitySlot).where(AvailabilitySlot.id == booking.slot_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    db.execute(update(Payment).where(Payment.id == payment.id).values(status=Payment.status))
    db.refresh(payment)
    return booking


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
    payment = db.get(Payment, event.payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if payment.provider != adapter.name:
        raise HTTPException(409, "Провайдер платежа не совпадает")
    _lock_payment_context(db, payment)
    seen = db.get(PaymentWebhookEvent, event.event_id)
    if seen:
        if seen.payment_id != payment.id or seen.status != event.status:
            raise HTTPException(409, "Событие уже использовано для другого уведомления")
        return json.loads(seen.response_json)
    booking = db.get(Booking, payment.booking_id)
    if event.status == "succeeded":
        if payment.status in {"pending", "failed"}:
            payment.status = "succeeded"
            adapter.ledger.on_capture(payment.id, payment.amount_rub)
            _confirm_captured_booking(db, payment, booking)
    elif event.status == "failed" and payment.status == "pending":
        payment.status = "failed"
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
    if (
        not settings.allow_default_webhook_secret
        and settings.webhook_secret == "dev-webhook-secret"
    ):
        raise HTTPException(503, "Webhook-секрет не настроен")
    return _apply_payment_webhook(body, db)


@router.post("/payments/{payment_id}/stub-complete")
def stub_complete(
    payment_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    webhook_limiter.check(f"payment-test-complete:{user.id}")
    if not payment_stub_enabled():
        raise HTTPException(403, "Тестовая оплата отключена")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    booking = db.get(Booking, payment.booking_id)
    event = db.get(Event, booking.event_id) if booking else None
    if not event:
        raise HTTPException(404, "Событие платежа не найдено")
    require_org_writer(db, user, event.organization_id)
    if payment.provider != "stub":
        raise HTTPException(409, "Платёж не является тестовым")
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


def _confirm_captured_booking(db: Session, payment: Payment, booking: Booking | None) -> None:
    """Capture is a money fact; expired/conflicting reservations need an operator."""
    if booking and booking.status in {"Confirmed", "InProgress", "Completed"}:
        return
    try:
        if not booking or booking.status != "AwaitingPayment":
            raise HTTPException(409, "Сделка закрыта или не ожидает оплаты")
        event = db.get(Event, booking.event_id)
        offer = db.get(Offer, booking.offer_id)
        req = db.get(DealRequest, offer.request_id)
        version = _require_contract_reservation(db, booking, event, offer, req)
        if version.total_rub != payment.amount_rub:
            raise HTTPException(409, "Сумма оплаты не соответствует условиям")
    except HTTPException as exc:
        audit(db, actor_user_id=None, action="payment.reservation_conflict",
              entity_type="payment", entity_id=payment.id,
              payload={"booking_id": booking.id if booking else None, "requires_operator": True, "reason": str(exc.detail)})
        return
    db.execute(update(AvailabilitySlot).where(AvailabilitySlot.id == booking.slot_id).values(status="confirmed"))
    for hold in db.query(BookingHold).filter_by(booking_id=booking.id, slot_id=booking.slot_id, status="active").all():
        hold.status = "consumed"
    _transition(booking, "Confirmed")
    attribute_booking(db, booking)
    conv = db.query(Conversation).filter_by(booking_id=booking.id).one_or_none()
    if conv:
        note = ("Тестовая оплата подтверждена. Деньги не списывались." if payment.provider == "stub"
                else "Оплата подтверждена. Бронирование подтверждено.")
        db.add(Message(conversation_id=conv.id, kind="system", body=note))


def capture_payment_as_succeeded(
    db: Session,
    *,
    payment: Payment,
    actor_user_id: str | None,
    event_id: str,
    note: str,
) -> dict:
    """Shared capture path for stub webhook / external admin confirm."""
    _lock_payment_context(db, payment)
    seen = db.get(PaymentWebhookEvent, event_id)
    if seen:
        if seen.payment_id != payment.id or seen.status != "succeeded":
            raise HTTPException(409, "Событие уже использовано")
        return json.loads(seen.response_json)
    booking = db.get(Booking, payment.booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    if payment.status not in {"pending", "failed", "succeeded"}:
        raise HTTPException(409, "Платёж уже закрыт")
    if payment.status != "succeeded":
        payment.status = "succeeded"
        _confirm_captured_booking(db, payment, booking)
    response = {
        "ok": True,
        "payment_id": payment.id,
        "payment_status": payment.status,
        "booking_status": booking.status,
    }
    db.add(
        PaymentWebhookEvent(
            event_id=event_id,
            payment_id=payment.id,
            status="succeeded",
            response_json=json.dumps(response),
        )
    )
    audit(
        db,
        actor_user_id=actor_user_id,
        action="payment.captured",
        entity_type="payment",
        entity_id=payment.id,
        payload=response,
    )
    db.commit()
    return response
