"""Commercial lifecycle; expiry does not depend on a successful payment transport."""

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import free_code, get_plan
from booker_api.commerce.entitlements import get_subscription
from booker_api.commerce.orders import lock_organization
from booker_api.commerce.provider import ProviderUnavailable, get_provider
from booker_api.models import BillingOrder, Organization, Subscription
from booker_api.security import audit, aware, now


def subscription_payload(sub: Subscription | None) -> dict | None:
    if sub is None:
        return None
    return {
        "id": sub.id,
        "organization_id": sub.organization_id,
        "plan_code": sub.plan_code,
        "status": sub.status,
        "billing_period": sub.billing_period,
        "starts_at": aware(sub.starts_at),
        "current_period_end": aware(sub.current_period_end),
        "cancel_at_period_end": sub.cancel_at_period_end,
        "next_plan_code": sub.next_plan_code,
        "provider": sub.provider,
    }


def expire_subscriptions(db: Session, organization_id: str | None = None, *, limit: int | None = None) -> int:
    query = db.query(Subscription).filter(
        Subscription.status.in_(["active", "trial", "past_due"]),
        Subscription.current_period_end <= now(),
    )
    if organization_id:
        query = query.filter(Subscription.organization_id == organization_id)
    count = 0
    if limit is not None:
        query = query.order_by(Subscription.current_period_end, Subscription.id).limit(limit)
    for sub in query.all():
        status = "cancelled" if sub.cancel_at_period_end else "expired"
        changed = db.execute(
            update(Subscription)
            .where(
                Subscription.id == sub.id,
                Subscription.status == sub.status,
                Subscription.current_period_end <= now(),
            )
            .values(status=status)
            .execution_options(synchronize_session="fetch")
        )
        if not changed.rowcount:
            continue
        count += 1
        from booker_api.notifications.lifecycle import commerce_href, organization_notice
        organization_notice(db, sub.organization_id, template='subscription.expired', subject='Период подписки завершён',
            body='Платный период завершён. Проверьте текущий тариф и доступные функции в кабинете. Условия уже согласованных сделок сохраняются.',
            entity_type='subscription', entity_id=sub.id, key=aware(sub.current_period_end).isoformat(), href=commerce_href(db, sub.organization_id))
        audit(
            db,
            actor_user_id=None,
            action="subscription.expired",
            entity_type="organization",
            entity_id=sub.organization_id,
            payload={"plan_code": sub.plan_code, "next_plan_code": sub.next_plan_code},
        )
    return count


def schedule_change(db: Session, organization_id: str, plan_code: str, actor_id: str) -> dict:
    lock_organization(db, organization_id)
    org = db.get(Organization, organization_id)
    target = get_plan(db, plan_code)
    if target.audience != org.kind:
        raise HTTPException(422, "Тариф не подходит организации")
    sub = get_subscription(db, organization_id)
    if not sub or sub.status not in {"active", "trial"} or aware(sub.current_period_end) <= now():
        raise HTTPException(409, "Действующей подписки нет")
    current = get_plan(db, sub.plan_code)
    if target.sort_order >= current.sort_order:
        raise HTTPException(422, "Для повышения тарифа выберите новый заказ")
    if sub.next_plan_code == target.code and sub.cancel_at_period_end:
        return subscription_payload(sub)
    if sub.provider_subscription_id:
        provider = get_provider()
        if provider.name != sub.provider:
            raise HTTPException(503, "Изменение автопродления временно недоступно")
        try:
            provider.cancel_subscription(sub.provider_subscription_id)
        except ProviderUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    sub.next_plan_code = plan_code
    sub.cancel_at_period_end = True
    audit(
        db,
        actor_user_id=actor_id,
        action="subscription.cancelled",
        entity_type="organization",
        entity_id=organization_id,
        payload={"effective_at": sub.current_period_end.isoformat(), "next_plan_code": plan_code},
    )
    return subscription_payload(sub)


def cancel_order(db: Session, order: BillingOrder, actor_id: str) -> None:
    lock_organization(db, order.organization_id)
    db.refresh(order)
    if order.status == "cancelled":
        return
    if order.status not in {"created", "pending_payment", "failed"}:
        raise HTTPException(409, "Оплаченный заказ отменяется через возврат и поддержку")
    order.status = "cancelled"
    order.cancelled_at = now()
    if order.product_kind == "promotion":
        from booker_api.commerce.promotions import settle_campaign

        settle_campaign(db, order)
    audit(
        db,
        actor_user_id=actor_id,
        action="billing.cancelled",
        entity_type="billing_order",
        entity_id=order.id,
        payload={"organization_id": order.organization_id},
    )


def cancel_subscription(db: Session, organization_id: str, actor_id: str) -> dict:
    org = db.get(Organization, organization_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    return schedule_change(db, organization_id, free_code(org.kind), actor_id)
