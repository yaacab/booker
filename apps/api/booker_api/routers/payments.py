import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.contract_ack import (
    EFFECT,
    LEGAL_PACK_VERSION,
    TEMPLATE_VERSION,
    body_hash,
    check_challenge,
    new_challenge,
    render_contract,
)
from booker_api.db import get_db
from booker_api.external_evidence import append_event, reserve_version, safe_note
from booker_api.models import (
    AvailabilitySlot,
    Booking,
    Contract,
    ContractChallenge,
    ContractSignature,
    Conversation,
    Event,
    EventTeamRequirement,
    ExternalPaymentEvent,
    ExternalPaymentReport,
    Message,
    Offer,
    OfferVersion,
    Organization,
    Payment,
    PaymentObligation,
    PaymentWebhookEvent,
    TeamMember,
    User,
    new_id,
)
from booker_api.models import Request as BookingRequest
from booker_api.money_movements import append_money_movement
from booker_api.notifications.service import notify
from booker_api.notifications.types import Channel, Notification
from booker_api.payment_obligations import (
    ensure_payment_plan,
    mark_obligation_satisfied,
    obligation_for_payment,
)
from booker_api.payments.adapter import PaymentAdapterError, get_payment_adapter
from booker_api.rate_limit import client_key, otp_limiter, webhook_limiter
from booker_api.routers.deals import (
    _booking_participant_orgs,
    _resolve_acting_party,
    _transition,
)
from booker_api.schemas import (
    ExternalPaymentAckIn,
    ExternalPaymentCorrectionIn,
    ExternalPaymentReportIn,
    PaymentIn,
    SignIn,
    WebhookIn,
)
from booker_api.security import audit, aware, current_user, membership

router = APIRouter(tags=["payments"])


def _contract_transaction_snapshot(
    db: Session,
    *,
    booking: Booking,
    offer: Offer,
    customer_org_id: str,
    supplier_org_id: str,
) -> dict[str, object]:
    event = db.get(Event, booking.event_id)
    request_row = db.get(BookingRequest, offer.request_id)
    requirement = (
        db.get(EventTeamRequirement, request_row.requirement_id)
        if request_row and request_row.requirement_id
        else None
    )
    slot = db.get(AvailabilitySlot, booking.slot_id)
    customer_org = db.get(Organization, customer_org_id)
    supplier_org = db.get(Organization, supplier_org_id)
    if not event or not request_row or not slot or not customer_org or not supplier_org:
        raise HTTPException(409, "Нельзя сформировать полный снимок предмета сделки")
    return {
        "booking_id": booking.id,
        "customer": {"organization_id": customer_org.id, "name": customer_org.name},
        "event": {
            "city": event.city,
            "event_date": event.event_date.isoformat(),
            "event_id": event.id,
            "title": event.title,
        },
        "request": {
            "request_id": request_row.id,
            "resource_id": request_row.resource_id,
            "resource_type": request_row.resource_type,
        },
        "requirement": None if not requirement else {
            "category_code": requirement.category_code,
            "notes": requirement.notes,
            "qty": requirement.qty,
            "requirement_id": requirement.id,
            "role_label": requirement.role_label,
        },
        "slot": {
            "ends_at": slot.ends_at.isoformat(),
            "slot_id": slot.id,
            "starts_at": slot.starts_at.isoformat(),
        },
        "supplier": {"organization_id": supplier_org.id, "name": supplier_org.name},
    }


def _render_booking_contract(
    db: Session,
    *,
    booking: Booking,
    offer: Offer,
    version: OfferVersion,
    customer_org_id: str,
    supplier_org_id: str,
) -> str:
    return render_contract(
        version,
        transaction=_contract_transaction_snapshot(
            db,
            booking=booking,
            offer=offer,
            customer_org_id=customer_org_id,
            supplier_org_id=supplier_org_id,
        ),
    )


def _challenge_was_delivered(results: list[dict]) -> bool:
    return any(
        result.get("sent") is True
        or (
            result.get("channel") == "in_app"
            and result.get("provider") == "dev"
            and result.get("status") == "logged"
        )
        for result in results
    )


def _active_challenge_delivery(db: Session, contract_id: str) -> dict[str, bool]:
    sides = {
        row[0]
        for row in db.query(ContractChallenge.side).filter(
            ContractChallenge.contract_id == contract_id,
            ContractChallenge.consumed_at.is_(None),
            ContractChallenge.expires_at > datetime.now(timezone.utc),
        ).all()
    }
    return {"customer": "customer" in sides, "supplier": "supplier" in sides}


def _contract_signature_sides(db: Session, contract: Contract) -> set[str]:
    if not contract.offer_version_id or not contract.body_sha256:
        return set()
    return {
        row[0]
        for row in db.query(ContractSignature.side).filter(
            ContractSignature.contract_id == contract.id,
            ContractSignature.offer_version_id == contract.offer_version_id,
            ContractSignature.body_sha256 == contract.body_sha256,
            ContractSignature.effect == EFFECT,
            ContractSignature.actor_user_id.is_not(None),
        ).all()
    }

@router.post("/bookings/{booking_id}/contract")
def create_contract(
    booking_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    event = (
        db.query(Event)
        .filter(Event.id == booking.event_id)
        .with_for_update()
        .one_or_none()
    )
    if not event:
        raise HTTPException(404, "Событие не найдено")
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    creator = membership(db, user.id, customer_org_id)
    if creator is None or creator.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Нет права создавать договор этой брони")
    if booking.status not in {"DateHeld", "AwaitingContract"}:
        raise HTTPException(409, "Сначала удержите дату")
    offer = db.query(Offer).filter_by(id=booking.offer_id).with_for_update().one_or_none()
    if offer:
        db.refresh(booking)
    version = (
        db.get(OfferVersion, booking.accepted_offer_version_id)
        if booking.accepted_offer_version_id
        else None
    )
    if (
        not offer
        or not version
        or version.offer_id != offer.id
        or version.id != offer.active_version_id
        or not (version.customer_ack and version.supplier_ack)
    ):
        raise HTTPException(409, "Нет действующей принятой версии предложения")
    existing = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    if existing:
        delivery = _active_challenge_delivery(db, existing.id)
        return {
            "id": existing.id,
            "body": existing.body,
            "body_sha256": existing.body_sha256,
            "offer_version_id": existing.offer_version_id,
            "effect": existing.effect,
            "status": booking.status,
            "otp_delivered": all(delivery.values()),
            "otp_delivery": delivery,
        }
    body = _render_booking_contract(
        db,
        booking=booking,
        offer=offer,
        version=version,
        customer_org_id=customer_org_id,
        supplier_org_id=supplier_org_id,
    )
    ensure_payment_plan(db, version)
    contract = Contract(
        booking_id=booking.id,
        body=body,
        offer_version_id=version.id,
        body_sha256=body_hash(body),
        template_key=TEMPLATE_VERSION,
        effect=EFFECT,
        legal_pack_version=LEGAL_PACK_VERSION,
    )
    db.add(contract)
    db.flush()
    _transition(booking, "AwaitingContract")
    conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
    delivered_sides: set[str] = set()
    for side, org_id in (("customer", customer_org_id), ("supplier", supplier_org_id)):
        members = db.query(TeamMember).filter(TeamMember.organization_id == org_id).all()
        for member in members:
            if member.role not in {"owner", "admin", "manager"}:
                continue
            recipient = db.get(User, member.user_id)
            if not recipient:
                continue
            code, code_hash, expires_at = new_challenge()
            challenge_id = new_id()
            results = notify(
                db,
                actor_user_id=user.id,
                notifications=[Notification(
                    channel=channel, template="contract.otp",
                    recipient_user_id=recipient.id, recipient_email=recipient.email,
                    subject="Код подтверждения черновика условий",
                    body=f"Ваш код технического подтверждения черновика в Букере: {code}",
                    entity_type="contract", entity_id=contract.id,
                    metadata={
                        "delivery_id": challenge_id,
                        "ephemeral_secret": True,
                        "expires_at": expires_at.isoformat(),
                    },
                ) for channel in (Channel.IN_APP, Channel.EMAIL)],
            )
            if not _challenge_was_delivered(results):
                continue
            db.add(ContractChallenge(
                id=challenge_id,
                contract_id=contract.id,
                side=side,
                actor_user_id=recipient.id,
                otp_hash=code_hash,
                expires_at=expires_at,
            ))
            delivered_sides.add(side)
    delivery = {
        "customer": "customer" in delivered_sides,
        "supplier": "supplier" in delivered_sides,
    }
    if all(delivery.values()):
        delivery_message = "Коды отправлены уполномоченным участникам обеих сторон."
    elif any(delivery.values()):
        delivery_message = "Код доставлен только одной стороне; второй стороне нужно запросить свой код."
    else:
        delivery_message = "Коды не доставлены; сторонам нужно запросить их после восстановления канала."
    db.add(Message(
        conversation_id=conv.id,
        kind="system",
        body=f"Черновик условий готов к техническому подтверждению. {delivery_message}",
    ))
    audit(
        db,
        actor_user_id=user.id,
        action="contract.created",
        entity_type="contract",
        entity_id=contract.id,
        payload={"delivery": delivery},
    )
    db.commit()
    db.refresh(contract)
    return {
        "id": contract.id,
        "body": contract.body,
        "body_sha256": contract.body_sha256,
        "offer_version_id": contract.offer_version_id,
        "effect": contract.effect,
        "status": booking.status,
        "otp_delivered": all(delivery.values()),
        "otp_delivery": delivery,
    }


@router.post("/contracts/{contract_id}/sign")
def sign_contract(
    contract_id: str,
    body: SignIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Договор не найден")
    booking = db.get(Booking, contract.booking_id)
    offer = db.query(Offer).filter_by(id=booking.offer_id).with_for_update().one_or_none()
    if offer:
        db.refresh(contract)
        db.refresh(booking)
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    side, acting_org_id, member = _resolve_acting_party(
        db,
        user,
        customer_org_id,
        supplier_org_id,
        x_booker_org=x_booker_org,
        claimed_side=body.side,
        writer_required=True,
    )
    version = db.get(OfferVersion, contract.offer_version_id) if contract.offer_version_id else None
    if (
        booking.status != "AwaitingContract" or contract.effect != EFFECT
        or not version or not offer or version.offer_id != offer.id
        or booking.accepted_offer_version_id != version.id
        or offer.active_version_id != version.id
        or not (version.customer_ack and version.supplier_ack)
        or contract.body_sha256 != body_hash(contract.body)
        or body.body_hash != contract.body_sha256
    ):
        raise HTTPException(409, "Черновик или версия предложения изменились")
    otp_limiter.check(f"contract:otp:{contract.id}:{user.id}")
    challenge = (
        db.query(ContractChallenge)
        .filter_by(contract_id=contract.id, side=side, actor_user_id=user.id)
        .filter(ContractChallenge.consumed_at.is_(None))
        .order_by(ContractChallenge.expires_at.desc(), ContractChallenge.id.desc())
        .first()
    )
    now = datetime.now(timezone.utc)
    if (
        not challenge or challenge.consumed_at is not None
        or aware(challenge.expires_at) <= now
        or not check_challenge(body.otp, challenge.otp_hash)
    ):
        raise HTTPException(403, "Неверный или просроченный OTP")
    if (side == "customer" and contract.customer_signed) or (side == "supplier" and contract.supplier_signed):
        raise HTTPException(409, "Эта сторона уже подтвердила черновик")
    if side == "customer":
        if (
            db.query(ContractSignature.id)
            .filter_by(contract_id=contract.id, actor_user_id=user.id, side="supplier")
            .first()
        ):
            raise HTTPException(409, "Один пользователь не может подписать обе стороны")
        if not contract.customer_signed:
            db.add(
                ContractSignature(
                    contract_id=contract.id,
                    side="customer",
                    organization_id=acting_org_id,
                    actor_user_id=user.id,
                    actor_role_snapshot=member.role,
                    offer_version_id=version.id,
                    body_sha256=contract.body_sha256,
                    effect=EFFECT,
                )
            )
            contract.customer_signed = True
    else:
        if (
            db.query(ContractSignature.id)
            .filter_by(contract_id=contract.id, actor_user_id=user.id, side="customer")
            .first()
        ):
            raise HTTPException(409, "Один пользователь не может подписать обе стороны")
        if not contract.supplier_signed:
            db.add(
                ContractSignature(
                    contract_id=contract.id,
                    side="supplier",
                    organization_id=acting_org_id,
                    actor_user_id=user.id,
                    actor_role_snapshot=member.role,
                    offer_version_id=version.id,
                    body_sha256=contract.body_sha256,
                    effect=EFFECT,
                )
            )
            contract.supplier_signed = True
    challenge.consumed_at = now
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Подпись этой стороны уже зафиксирована") from exc
    if contract.customer_signed and contract.supplier_signed and booking.status == "AwaitingContract":
        _transition(booking, "AwaitingPayment")
        conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
        db.add(Message(conversation_id=conv.id, kind="system", body="Обе стороны технически подтвердили черновик условий. Ожидается предоплата."))
    audit(
        db,
        actor_user_id=user.id,
        action="contract.draft_acknowledged",
        entity_type="contract",
        entity_id=contract.id,
        payload={"side": side, "acting_org_id": acting_org_id},
    )
    db.commit()
    return {
        "customer_signed": contract.customer_signed,
        "supplier_signed": contract.supplier_signed,
        "booking_status": booking.status,
    }


@router.post("/contracts/{contract_id}/challenge")
def reissue_contract_challenge(
    contract_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    """Issue a new append-only challenge after the previous one expired or was consumed."""
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Черновик не найден")
    booking = db.get(Booking, contract.booking_id)
    offer = db.query(Offer).filter_by(id=booking.offer_id).with_for_update().one_or_none()
    if offer:
        db.refresh(contract)
        db.refresh(booking)
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    side, acting_org_id, _member = _resolve_acting_party(
        db, user, customer_org_id, supplier_org_id,
        x_booker_org=x_booker_org, claimed_side=None, writer_required=True,
    )
    version = db.get(OfferVersion, contract.offer_version_id) if contract.offer_version_id else None
    if (
        booking.status != "AwaitingContract" or contract.effect != EFFECT
        or not version or not offer or version.offer_id != offer.id
        or booking.accepted_offer_version_id != version.id or offer.active_version_id != version.id
        or not (version.customer_ack and version.supplier_ack)
        or contract.body_sha256 != body_hash(contract.body)
        or (side == "customer" and contract.customer_signed)
        or (side == "supplier" and contract.supplier_signed)
    ):
        raise HTTPException(409, "Черновик или версия предложения изменились")
    otp_limiter.check(f"contract:otp-issue:{contract.id}:{user.id}")
    now = datetime.now(timezone.utc)
    active = (
        db.query(ContractChallenge.id)
        .filter_by(contract_id=contract.id, side=side, actor_user_id=user.id)
        .filter(ContractChallenge.consumed_at.is_(None), ContractChallenge.expires_at > now)
        .first()
    )
    if active:
        raise HTTPException(409, "Текущий код ещё действует")
    code, code_hash, expires_at = new_challenge()
    challenge_id = new_id()
    notifications = [
        Notification(
            channel=channel,
            template="contract.otp",
            recipient_user_id=user.id,
            recipient_email=user.email,
            subject="Новый код подтверждения черновика условий",
            body=f"Ваш новый код технического подтверждения черновика в Букере: {code}",
            entity_type="contract",
            entity_id=contract.id,
            metadata={
                "delivery_id": challenge_id,
                "ephemeral_secret": True,
                "expires_at": expires_at.isoformat(),
            },
        )
        for channel in (Channel.IN_APP, Channel.EMAIL)
    ]
    results = notify(db, actor_user_id=user.id, notifications=notifications)
    if not _challenge_was_delivered(results):
        db.rollback()
        raise HTTPException(503, "Код не доставлен; повторите запрос позже")
    db.add(ContractChallenge(
        id=challenge_id,
        contract_id=contract.id,
        side=side,
        actor_user_id=user.id,
        otp_hash=code_hash,
        expires_at=expires_at,
    ))
    audit(
        db,
        actor_user_id=user.id,
        action="contract.draft_challenge_issued",
        entity_type="contract",
        entity_id=contract.id,
        payload={"side": side, "acting_org_id": acting_org_id},
    )
    db.commit()
    return {"otp_delivered": True, "expires_at": expires_at.isoformat(), "effect": EFFECT}


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
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    customer_org_id, _supplier_org_id = _booking_participant_orgs(db, booking)
    payer = membership(db, user.id, customer_org_id)
    if payer is None or payer.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Нет права оплачивать эту бронь")
    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).one_or_none()
    if existing:
        if existing.booking_id != booking.id:
            raise HTTPException(409, "Ключ повторного запроса уже использован")
        if body.obligation_id and existing.obligation_id != body.obligation_id:
            raise HTTPException(409, "Ключ повторного запроса относится к другому обязательству")
        return {"id": existing.id, "status": existing.status, "idempotent": True}
    offer = db.query(Offer).filter_by(id=booking.offer_id).with_for_update().one_or_none()
    if offer:
        db.refresh(booking)
    version = (
        db.get(OfferVersion, booking.accepted_offer_version_id)
        if booking.accepted_offer_version_id
        else None
    )
    contract = db.query(Contract).filter(Contract.booking_id == booking.id).one_or_none()
    if (
        not offer
        or not version
        or version.offer_id != offer.id
        or version.id != offer.active_version_id
        or not contract
        or not (contract.customer_signed and contract.supplier_signed)
        or contract.offer_version_id != version.id
        or contract.effect != EFFECT
        or not contract.body_sha256
        or contract.body_sha256 != body_hash(contract.body)
        or _contract_signature_sides(db, contract) != {"customer", "supplier"}
    ):
        raise HTTPException(409, "Принятая версия и технически подтверждённый черновик не совпадают")
    try:
        obligation = obligation_for_payment(
            db,
            version=version,
            obligation_id=body.obligation_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    obligation = (
        db.query(PaymentObligation)
        .filter(PaymentObligation.id == obligation.id)
        .with_for_update()
        .one()
    )
    allowed_statuses = {"AwaitingPayment"} if obligation.kind == "advance" else {
        "Confirmed",
        "InProgress",
    }
    if booking.status not in allowed_statuses:
        raise HTTPException(409, "Это платежное обязательство сейчас недоступно")
    if obligation.status != "pending" or obligation.amount_rub <= 0:
        raise HTTPException(409, "Платежное обязательство уже выполнено или не применяется")
    active_payment = (
        db.query(Payment)
        .filter(
            Payment.obligation_id == obligation.id,
            Payment.status.in_(["pending", "succeeded", "external_recorded"]),
        )
        .first()
    )
    if active_payment:
        raise HTTPException(409, "Для обязательства уже существует платеж")
    pay = Payment(
        booking_id=booking.id,
        obligation_id=obligation.id,
        amount_rub=obligation.amount_rub,
        status="pending",
        provider=adapter.name,
        provider_merchant=(settings.payment_merchant_id or "").strip() or adapter.name,
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
    pay.provider_reference = session.provider_reference
    audit(
        db,
        actor_user_id=user.id,
        action="payment.created",
        entity_type="payment",
        entity_id=pay.id,
        payload={
            "amount_rub": pay.amount_rub,
            "provider": session.provider,
            "obligation_id": obligation.id,
            "obligation_kind": obligation.kind,
        },
    )
    db.commit()
    db.refresh(pay)
    return {
        "id": pay.id,
        "status": pay.status,
        "amount_rub": pay.amount_rub,
        "obligation_id": obligation.id,
        "obligation_kind": obligation.kind,
    }


@router.post("/payments/{payment_id}/external-report")
def submit_external_report(
    payment_id: str,
    body: ExternalPaymentReportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    booking = db.get(Booking, payment.booking_id)
    if not booking:
        raise HTTPException(404, "Событие платежа не найдено")
    customer_org_id, _supplier_org_id = _booking_participant_orgs(db, booking)
    payer = membership(db, user.id, customer_org_id)
    if payer is None or payer.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Нет права сообщать о внешнем переводе")
    if payment.provider != "external":
        raise HTTPException(409, "Платёж не в режиме external")
    key = body.idempotency_key.strip()
    reference = body.reference.strip()
    if not key or len(reference) < 3:
        raise HTTPException(400, "Укажите ключ запроса и реквизиты операции")
    existing = db.query(ExternalPaymentReport).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if existing.payment_id != payment.id or existing.submitted_by_user_id != user.id:
            raise HTTPException(409, "Ключ повторного запроса уже использован")
        if existing.reference != reference or existing.details != body.details.strip():
            raise HTTPException(409, "Ключ повторного запроса уже использован с другими сведениями")
        return {"id": existing.id, "status": existing.status, "idempotent": True}
    obligation = db.get(PaymentObligation, payment.obligation_id) if payment.obligation_id else None
    allowed_booking_status = (
        booking.status == "AwaitingPayment"
        if not obligation or obligation.kind == "advance"
        else booking.status in {"Confirmed", "InProgress"}
    )
    if payment.status != "pending" or not allowed_booking_status:
        raise HTTPException(409, "Сведения доступны только для ожидаемого внешнего платежа")
    latest = (
        db.query(ExternalPaymentReport)
        .filter_by(payment_id=payment.id)
        .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
        .first()
    )
    if latest and latest.status == "submitted":
        raise HTTPException(409, "Сведения уже ожидают проверки")
    report = ExternalPaymentReport(
        payment_id=payment.id,
        idempotency_key=key,
        submitted_by_user_id=user.id,
        reference=reference,
        details=body.details.strip(),
    )
    db.add(report)
    db.flush()
    version = payment.external_evidence_version or 0
    reserve_version(db, payment, version)
    append_event(db, payment=payment, report_id=report.id, kind="payer_reported",
                 idempotency_key=f"payer:{report.id}", expected_version=version,
                 actor_user_id=user.id)
    audit(db, actor_user_id=user.id, action="payment.external_report_submitted", entity_type="payment", entity_id=payment.id, payload={"report_id": report.id})
    db.commit()
    return {"id": report.id, "status": report.status, "payment_status": payment.status,
            "evidence_version": version + 1}


@router.post("/payments/{payment_id}/external-reports/{report_id}/recipient-ack")
def acknowledge_external_report(
    payment_id: str,
    report_id: str,
    body: ExternalPaymentAckIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payment = db.get(Payment, payment_id)
    report = db.get(ExternalPaymentReport, report_id)
    if not payment or payment.provider != "external" or not report or report.payment_id != payment.id:
        raise HTTPException(404, "Сведения о внешнем переводе не найдены")
    booking = db.get(Booking, payment.booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    _customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    supplier = membership(db, user.id, supplier_org_id)
    if supplier is None or supplier.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Нет права подтверждать получение сведений")
    if user.id == report.submitted_by_user_id:
        raise HTTPException(403, "Нужен другой участник со стороны получателя")
    key = "recipient:" + body.idempotency_key.strip()
    existing = db.query(ExternalPaymentEvent).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if (existing.payment_id != payment.id or existing.report_id != report.id
                or existing.actor_user_id != user.id or existing.kind != "recipient_acknowledged"):
            raise HTTPException(409, "Ключ уже использован")
        return {"event_id": existing.id, "status": "recipient_acknowledged", "idempotent": True}
    latest = (db.query(ExternalPaymentReport).filter_by(payment_id=payment.id)
              .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
              .first())
    if payment.status != "pending" or report.status != "submitted" or latest.id != report.id:
        raise HTTPException(409, "Сведения уже изменились")
    if db.query(ExternalPaymentEvent).filter_by(
        report_id=report.id, kind="recipient_acknowledged"
    ).first():
        raise HTTPException(409, "Получатель уже подтвердил сведения")
    version = payment.external_evidence_version or 0
    reserve_version(db, payment, version)
    event = append_event(db, payment=payment, report_id=report.id,
                         kind="recipient_acknowledged", idempotency_key=key,
                         expected_version=version, actor_user_id=user.id)
    audit(db, actor_user_id=user.id, action="payment.recipient_acknowledged",
          entity_type="payment", entity_id=payment.id, payload={"report_id": report.id,
                                                                 "event_id": event.id})
    db.commit()
    return {"event_id": event.id, "status": "recipient_acknowledged",
            "evidence_version": version + 1}


@router.post("/payments/{payment_id}/external-corrections")
def request_external_correction(
    payment_id: str,
    body: ExternalPaymentCorrectionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payment = db.get(Payment, payment_id)
    if not payment or payment.provider != "external":
        raise HTTPException(404, "Внешний платёж не найден")
    booking = db.get(Booking, payment.booking_id)
    if not booking:
        raise HTTPException(404, "Бронь не найдена")
    customer_org_id, supplier_org_id = _booking_participant_orgs(db, booking)
    if not (user.is_platform_admin or membership(db, user.id, customer_org_id)
            or membership(db, user.id, supplier_org_id)):
        raise HTTPException(403, "Нет доступа к сведениям этой сделки")
    report = db.get(ExternalPaymentReport, body.report_id)
    if not report or report.payment_id != payment.id:
        raise HTTPException(404, "Сведения о переводе не найдены")
    note = safe_note(body.note)
    key = "correction-request:" + body.idempotency_key.strip()
    existing = db.query(ExternalPaymentEvent).filter_by(idempotency_key=key).one_or_none()
    if existing:
        if (existing.kind != "correction_requested" or existing.payment_id != payment.id
                or existing.report_id != report.id or existing.actor_user_id != user.id
                or existing.expected_version != body.expected_version
                or existing.reason_code != body.reason_code or existing.note != note
                or existing.parent_event_id != (
                    None if body.target_event_id == report.id else body.target_event_id
                )):
            raise HTTPException(409, "Ключ запроса уже использован")
        return {"event_id": existing.id, "status": "correction_requested", "idempotent": True}
    latest = (db.query(ExternalPaymentReport).filter_by(payment_id=payment.id)
              .order_by(ExternalPaymentReport.created_at.desc(), ExternalPaymentReport.id.desc())
              .first())
    if report.status != "recorded" or latest.id != report.id:
        raise HTTPException(409, "Нужны последние проверенные сведения")
    target = db.get(ExternalPaymentEvent, body.target_event_id)
    if target:
        if (target.payment_id != payment.id or target.report_id != report.id
                or target.kind != "admin_evidence_reviewed"):
            raise HTTPException(409, "Целевое событие не соответствует отчёту")
    elif body.target_event_id != report.id:
        raise HTTPException(404, "Целевое событие не найдено")
    if db.query(ExternalPaymentEvent).filter_by(report_id=report.id,
                                               kind="correction_requested").first():
        raise HTTPException(409, "Исправление уже запрошено")
    reserve_version(db, payment, body.expected_version)
    event = append_event(
        db, payment=payment, report_id=report.id, kind="correction_requested",
        idempotency_key=key, expected_version=body.expected_version,
        actor_user_id=user.id, parent_event_id=target.id if target else None,
        reason_code=body.reason_code, note=note,
    )
    audit(db, actor_user_id=user.id, action="payment.external_correction_requested",
          entity_type="payment", entity_id=payment.id,
          payload={"report_id": report.id, "event_id": event.id,
                   "reason_code": body.reason_code})
    db.commit()
    return {"event_id": event.id, "status": "correction_requested",
            "evidence_version": body.expected_version + 1}


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
        raise HTTPException(409, "Webhook другого провайдера не может изменить платёж")
    seen = db.get(PaymentWebhookEvent, event.event_id)
    if seen:
        if seen.payment_id != payment.id:
            raise HTTPException(409, "event_id уже использован для другого платежа")
        return json.loads(seen.response_json)
    booking = db.get(Booking, payment.booking_id)
    obligation = db.get(PaymentObligation, payment.obligation_id) if payment.obligation_id else None
    terminal_statuses = {
        "succeeded",
        "failed",
        "external_recorded",
        "refunded",
        "partially_refunded",
    }
    if payment.status in terminal_statuses:
        response = {
            "ok": True,
            "payment_id": payment.id,
            "payment_status": payment.status,
            "booking_status": booking.status,
            "obligation_id": obligation.id if obligation else None,
            "obligation_status": obligation.status if obligation else None,
            "ignored_terminal_event": True,
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
            action="payment.webhook_ignored_terminal",
            entity_type="payment",
            entity_id=payment.id,
            payload=response,
        )
        db.commit()
        return response
    claimed = db.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.status == "pending")
        .values(status=event.status)
    ).rowcount
    if claimed != 1:
        db.expire(payment)
        db.refresh(payment)
        response = {
            "ok": True,
            "payment_id": payment.id,
            "payment_status": payment.status,
            "booking_status": booking.status,
            "obligation_id": obligation.id if obligation else None,
            "obligation_status": obligation.status if obligation else None,
            "ignored_terminal_event": True,
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
            action="payment.webhook_ignored_terminal",
            entity_type="payment",
            entity_id=payment.id,
            payload=response,
        )
        db.commit()
        return response
    payment.status = event.status
    if event.status == "succeeded":
        mark_obligation_satisfied(obligation)
        append_money_movement(
            db,
            payment=payment,
            kind="capture",
            direction="credit",
            amount_rub=payment.amount_rub,
            source_type="provider_event",
            source_id=event.event_id,
            metadata={"provider_status": event.status},
        )
        adapter.ledger.on_capture(payment.id, payment.amount_rub)
        if (not obligation or obligation.kind == "advance") and booking.status == "AwaitingPayment":
            _transition(booking, "Confirmed")
            slot = db.get(AvailabilitySlot, booking.slot_id)
            slot.status = "confirmed"
            conv = db.query(Conversation).filter(Conversation.booking_id == booking.id).one()
            db.add(
                Message(
                    conversation_id=conv.id,
                    kind="system",
                    body="Аванс получен. Бронирование подтверждено.",
                )
            )
    elif event.status == "failed":
        if booking.status != "Confirmed":
            pass
    response = {
        "ok": True,
        "payment_id": payment.id,
        "payment_status": payment.status,
        "booking_status": booking.status,
        "obligation_id": obligation.id if obligation else None,
        "obligation_status": obligation.status if obligation else None,
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
    if settings.payment_provider.strip().lower() not in {"", "stub"}:
        raise HTTPException(403, "Только stub-провайдер")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    if payment.provider != "stub":
        raise HTTPException(403, "Только stub-платёж")
    booking = db.get(Booking, payment.booking_id)
    if not booking:
        raise HTTPException(404, "Событие платежа не найдено")
    customer_org_id, _supplier_org_id = _booking_participant_orgs(db, booking)
    payer = membership(db, user.id, customer_org_id)
    if payer is None or payer.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Нет права оплачивать эту бронь")
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
