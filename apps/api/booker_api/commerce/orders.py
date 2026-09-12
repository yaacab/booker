"""Billing orders and settlement. Domain state changes only after verified events."""

import calendar
import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import get_plan, plan_payload
from booker_api.commerce.entitlements import get_subscription
from booker_api.commerce.provider import ProviderUnavailable, get_provider
from booker_api.models import BillingOrder, CommerceWebhookEvent, Organization, Subscription
from booker_api.security import audit, aware, now


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
        "checkout_url": meta.get("checkout_url"),
        "checkout_available": order.provider != "disabled",
        "billing_period": meta.get("billing_period"),
        "commercial_policy_version": meta.get("commercial_policy_version"),
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "refunded_at": order.refunded_at,
        "message": "Онлайн-оплата пока недоступна"
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
        return existing
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
    try:
        checkout = provider.create_subscription(
            order_id=order.id,
            amount_rub=amount,
            currency="RUB",
            billing_period=billing_period,
            idempotency_key=order.id,
        )
        order.provider_reference = checkout.reference
        order.status = "pending_payment"
        meta.update(
            checkout_url=checkout.url, subscription_reference=checkout.subscription_reference
        )
    except ProviderUnavailable:
        # A reviewable order exists; no fictitious checkout or paid entitlement.
        order.status = "created"
    order.metadata_json = json.dumps(meta)
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
    if event.status != order.status:
        allowed = {
            "pending_payment": {"paid", "failed"},
            "paid": {"refunded"},
        }
        if event.status not in allowed.get(order.status, set()):
            raise HTTPException(409, "Недопустимый переход статуса оплаты")
        order.status = event.status
        if event.status == "paid":
            order.paid_at = now()
            if order.product_kind == "subscription":
                _activate_subscription(db, order)
        elif event.status == "refunded":
            order.refunded_at = now()
            sub = get_subscription(db, order.organization_id)
            if sub and sub.last_billing_order_id == order.id:
                sub.status = "cancelled"
                sub.cancel_at_period_end = False
                sub.next_plan_code = None
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
    sub.status = "active"
    sub.starts_at = now()
    sub.current_period_end = period_end(sub.starts_at, sub.billing_period)
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
