"""Billing orders and settlement. Domain state changes only after verified events."""

import calendar
import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import get_plan, plan_payload
from booker_api.commerce.entitlements import get_subscription
from booker_api.commerce.provider import ProviderUnavailable, get_provider
from booker_api.models import (
    BillingOrder,
    CommerceWebhookEvent,
    Organization,
    PromotionCreditUse,
    Subscription,
    User,
)
from booker_api.security import audit, aware, now, require_org_member


def lock_organization(db: Session, org_id: str) -> None:
    # An actual no-op write serializes on SQLite too, where FOR UPDATE is ignored.
    found = db.execute(
        update(Organization).where(Organization.id == org_id).values(name=Organization.name)
    )
    if found.rowcount != 1:
        raise HTTPException(404, "Организация не найдена")


def period_end(starts_at: datetime, billing_period: str) -> datetime:
    months = 12 if billing_period == "annual" else 1
    total = starts_at.year * 12 + starts_at.month - 1 + months
    year, month = divmod(total, 12)
    month += 1
    day = min(starts_at.day, calendar.monthrange(year, month)[1])
    return starts_at.replace(year=year, month=month, day=day)


def order_payload(order: BillingOrder) -> dict:
    meta = json.loads(order.metadata_json)
    return {
        "id": order.id,
        "organization_id": order.organization_id,
        "product_kind": order.product_kind,
        "product_code": order.product_code,
        "amount_rub": order.amount_rub,
        "currency": order.currency,
        "status": order.status,
        "provider": order.provider,
        "test_mode": order.provider == "stub",
        "checkout_url": meta.get("checkout_url") if order.status == 'pending_payment' else None,
        "can_retry_checkout": order.status == 'created' and meta.get('checkout_state') in ('creating', 'uncertain'),
        "can_cancel": order.status in ('created', 'pending_payment', 'failed') and meta.get('checkout_state') not in ('creating', 'uncertain'),
        "checkout_available": order.provider != "disabled",
        "billing_period": meta.get("billing_period"),
        "period_start": aware(order.period_start) if order.period_start else None,
        "period_end": aware(order.period_end) if order.period_end else None,
        "renewal": order.subscription_parent_id is not None,
        "requires_operator": not order.entitlement_eligible,
        "commercial_policy_version": meta.get("commercial_policy_version"),
        "created_at": aware(order.created_at),
        "paid_at": aware(order.paid_at) if order.paid_at else None,
        "cancelled_at": aware(order.cancelled_at) if order.cancelled_at else None,
        "refunded_at": aware(order.refunded_at) if order.refunded_at else None,
        "message": "Ответ платёжного партнёра не получен. Повторите получение ссылки для этого заказа." if order.status == 'created' and meta.get('checkout_state') in ('creating', 'uncertain') else "Онлайн-оплата пока недоступна"
        if order.provider == "disabled"
        else (
            "Тестовый режим: реальные деньги не списываются" if order.provider == "stub" else None
        ),
    }


def create_subscription_order(
    db: Session,
    org_id: str,
    plan_code: str,
    billing_period: str,
    idempotency_key: str,
    actor_id: str,
) -> BillingOrder:
    lock_organization(db, org_id)
    existing = (
        db.query(BillingOrder)
        .filter_by(organization_id=org_id, idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        meta = json.loads(existing.metadata_json)
        if (
            existing.product_kind != "subscription"
            or existing.product_code != plan_code
            or meta.get("billing_period") != billing_period
        ):
            raise HTTPException(409, "Этот ключ уже использован для другого заказа")
        return resume_checkout(db, existing, actor_id)
    if (
        db.query(PromotionCreditUse)
        .filter_by(organization_id=org_id, idempotency_key=idempotency_key)
        .first()
    ):
        raise HTTPException(409, "Этот ключ уже использован для другого заказа")
    org = db.get(Organization, org_id)
    plan = get_plan(db, plan_code)
    if plan.audience != org.kind:
        raise HTTPException(422, "Тариф не подходит типу организации")
    amount = plan.annual_price_rub if billing_period == "annual" else plan.monthly_price_rub
    if amount <= 0:
        raise HTTPException(422, "Бесплатный тариф не требует оплаты")
    sub = get_subscription(db, org_id)
    if sub and sub.status in {"active", "trial"} and aware(sub.current_period_end) > now():
        current = get_plan(db, sub.plan_code)
        if plan.sort_order < current.sort_order:
            raise HTTPException(409, "Понижение тарифа оформляется на конец текущего периода")
        if plan.code == current.code:
            raise HTTPException(409, "Тариф уже действует; продление доступно в конце периода")
    pending = (
        db.query(BillingOrder)
        .filter(
            BillingOrder.organization_id == org_id,
            BillingOrder.product_kind == "subscription",
            BillingOrder.status.in_(["created", "pending_payment"]),
        )
        .first()
    )
    if pending:
        raise HTTPException(409, "Завершите или отмените предыдущий заказ тарифа")
    provider = get_provider()
    meta = {
        "billing_period": billing_period,
        "plan_snapshot": plan_payload(plan),
        "commercial_policy_version": plan_payload(plan)["commercial_policy_version"],
    }
    order = BillingOrder(
        organization_id=org_id,
        product_kind="subscription",
        product_code=plan.code,
        amount_rub=amount,
        provider=provider.name,
        idempotency_key=idempotency_key,
        metadata_json=json.dumps(meta),
    )
    db.add(order)
    db.flush()
    if sub is None:
        db.add(
            Subscription(
                organization_id=org_id,
                plan_code=plan.code,
                billing_period=billing_period,
                status="pending",
                starts_at=now(),
                current_period_end=now(),
                provider=provider.name,
            )
        )
    audit(
        db,
        actor_user_id=actor_id,
        action="subscription.checkout_started",
        entity_type="billing_order",
        entity_id=order.id,
        payload={
            "organization_id": org_id,
            "plan_code": plan.code,
            "amount_rub": amount,
            "provider": provider.name,
        },
    )
    return resume_checkout(db, order, actor_id)


def resume_checkout(db: Session, order: BillingOrder, actor_id: str) -> BillingOrder:
    """Persist identity before I/O; every retry uses the original provider key/price."""
    lock_organization(db, order.organization_id)
    db.refresh(order)
    meta = json.loads(order.metadata_json)
    if order.status != 'created' or order.provider_reference:
        return order
    provider = get_provider()
    if provider.name != order.provider:
        raise HTTPException(409, 'Заказ должен обработать исходный платёжный партнёр')
    if provider.name == 'disabled':
        return order
    meta['checkout_state'] = 'creating'
    order.metadata_json = json.dumps(meta)
    audit(db, actor_user_id=actor_id, action='billing.checkout_requested', entity_type='billing_order', entity_id=order.id)
    db.commit()  # Includes campaign/subscription and immutable catalog snapshot.
    lock_organization(db, order.organization_id)
    db.refresh(order)
    if order.status != 'created' or order.provider_reference:
        return order
    member = require_org_member(db, db.get(User, actor_id), order.organization_id)
    if member.role not in ('owner', 'admin'):
        raise HTTPException(403, 'Оплатой управляет владелец или администратор организации')
    meta = json.loads(order.metadata_json)
    try:
        if order.product_kind == 'subscription':
            previous = get_subscription(db, order.organization_id)
            if previous and previous.provider_subscription_id and previous.agreement_order_id != order.id:
                if previous.provider != provider.name:
                    raise ProviderUnavailable('Previous subscription belongs to another provider')
                agreement = db.get(BillingOrder, previous.agreement_order_id) if previous.agreement_order_id else None
                old_meta = json.loads(agreement.metadata_json) if agreement else {}
                if not old_meta.get('renewal_cancel_effective_at'):
                    # Cancellation is idempotent. A retry after a lost response
                    # repeats the same cancellation before creating the new plan.
                    provider.cancel_subscription(previous.provider_subscription_id)
                    previous.cancel_at_period_end = True
                    if agreement:
                        old_meta['renewal_cancel_effective_at'] = aware(previous.current_period_end).isoformat()
                        agreement.metadata_json = json.dumps(old_meta)
                    audit(db, actor_user_id=actor_id, action='subscription.cancelled',
                        entity_type='organization', entity_id=order.organization_id,
                        payload={'reason': 'replacement_checkout', 'billing_order_id': order.id})
        args = {'order_id': order.id, 'amount_rub': order.amount_rub,
            'currency': order.currency, 'idempotency_key': order.id}
        checkout = (provider.create_subscription(**args, billing_period=meta['billing_period'])
            if order.product_kind == 'subscription' else provider.create_checkout(**args))
        for value in (checkout.reference,):
            if not isinstance(value, str) or not value or len(value) > 128 or value != value.strip():
                raise ProviderUnavailable('Invalid checkout reference')
        if checkout.status != 'pending_payment':
            raise ProviderUnavailable('Checkout is not evidence of capture')
        if checkout.url is not None:
            url = urlsplit(checkout.url)
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ProviderUnavailable('Invalid checkout URL')
        if order.product_kind == 'subscription' and (not isinstance(checkout.subscription_reference, str)
            or not checkout.subscription_reference or len(checkout.subscription_reference) > 128):
            raise ProviderUnavailable('Missing subscription reference')
        with db.begin_nested():
            order.provider_reference = checkout.reference
            db.flush()
        order.status = 'pending_payment'
        meta.update(checkout_state='ready', checkout_url=checkout.url,
            subscription_reference=checkout.subscription_reference)
        audit(db, actor_user_id=actor_id, action='billing.checkout_ready', entity_type='billing_order', entity_id=order.id)
    except (ProviderUnavailable, TimeoutError, ConnectionError, ValueError, TypeError, IntegrityError):
        meta['checkout_state'] = 'uncertain'
        audit(db, actor_user_id=actor_id, action='billing.checkout_uncertain', entity_type='billing_order', entity_id=order.id)
    order.metadata_json = json.dumps(meta)
    db.commit()
    return order


def settle_event(db: Session, payload: bytes, signature: str) -> dict:
    provider = get_provider()
    event = provider.verify_webhook(payload, signature)
    order = db.get(BillingOrder, event.order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    lock_organization(db, order.organization_id)
    db.refresh(order)
    digest = hashlib.sha256(payload).hexdigest()
    prior = (
        db.query(CommerceWebhookEvent)
        .filter_by(provider=provider.name, event_id=event.event_id)
        .one_or_none()
    )
    if prior:
        if prior.payload_hash != digest:
            raise HTTPException(409, "Содержимое повторного уведомления изменилось")
        return json.loads(prior.response_json)
    if (
        order.provider != provider.name
        or order.provider_reference != event.reference
        or order.amount_rub != event.amount_rub
        or order.currency != event.currency
    ):
        raise HTTPException(409, "Уведомление не соответствует заказу")
    if event.status == 'paid' and order.paid_at and event.paid_at and aware(order.paid_at) != event.paid_at:
        raise HTTPException(409, 'Подтверждённая дата оплаты изменилась')
    if event.status != order.status:
        allowed = {
            "pending_payment": {"paid", "failed"},
            "paid": {"refunded"},
        }
        if event.status not in allowed.get(order.status, set()):
            raise HTTPException(409, "Недопустимый переход статуса оплаты")
        order.status = event.status
        if event.status == "paid":
            if not event.paid_at and not provider.test_mode:
                raise HTTPException(409, 'Партнёр не передал дату подтверждённой оплаты')
            paid_at = event.paid_at or now()
            if paid_at > now() + timedelta(minutes=5) or paid_at < aware(order.created_at) - timedelta(minutes=5):
                raise HTTPException(409, 'Дата оплаты не соответствует заказу')
            order.paid_at = paid_at
            if order.product_kind == "subscription":
                _activate_subscription(db, order)
        elif event.status == "refunded":
            order.refunded_at = now()
            sub = get_subscription(db, order.organization_id)
            if sub and sub.last_billing_order_id == order.id:
                sub.status = "cancelled"
                sub.cancel_at_period_end = False
                sub.next_plan_code = None
        if order.product_kind == "promotion":
            from booker_api.commerce.promotions import settle_campaign

            settle_campaign(db, order)
        audit(
            db,
            actor_user_id=None,
            action=f"billing.{event.status}",
            entity_type="billing_order",
            entity_id=order.id,
            payload={
                "organization_id": order.organization_id,
                "amount_rub": order.amount_rub,
                "provider": order.provider,
            },
        )
    result = {"order_id": order.id, "status": order.status, "test_mode": provider.test_mode}
    db.add(
        CommerceWebhookEvent(
            provider=provider.name,
            event_id=event.event_id,
            order_id=order.id,
            payload_hash=digest,
            response_json=json.dumps(result),
        )
    )
    db.flush()
    return result


def _activate_subscription(db: Session, order: BillingOrder) -> None:
    meta = json.loads(order.metadata_json)
    sub = get_subscription(db, order.organization_id)
    if sub is None:
        sub = Subscription(organization_id=order.organization_id)
        db.add(sub)
    sub.plan_code = order.product_code
    sub.billing_period = meta["billing_period"]
    order.period_start = order.paid_at
    order.period_end = period_end(aware(order.paid_at), sub.billing_period)
    sub.starts_at = order.period_start
    sub.current_period_end = order.period_end
    sub.status = 'active' if aware(sub.current_period_end) > now() else 'expired'
    sub.agreement_order_id = order.id
    sub.cancel_at_period_end = False
    sub.next_plan_code = None
    sub.provider = order.provider
    sub.provider_subscription_id = meta.get("subscription_reference")
    sub.last_billing_order_id = order.id
    audit(
        db,
        actor_user_id=None,
        action="subscription.activated",
        entity_type="organization",
        entity_id=order.organization_id,
        payload={"plan_code": sub.plan_code, "billing_order_id": order.id},
    )
