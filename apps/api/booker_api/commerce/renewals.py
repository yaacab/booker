"""Verified recurring cycles: fixed agreement price, calendar periods, no new charges."""
import calendar
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from booker_api.commerce.entitlements import get_subscription
from booker_api.commerce.orders import lock_organization
from booker_api.commerce.provider import get_provider
from booker_api.models import BillingOrder, CommerceWebhookEvent
from booker_api.security import audit, aware, now


def cycle_boundary(anchor, billing_period, number):
    months = (12 if billing_period == 'annual' else 1) * number
    year, month = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
    month += 1
    return anchor.replace(year=year, month=month, day=min(anchor.day, calendar.monthrange(year, month)[1]))


def settle_renewal(db, payload, signature):
    provider = get_provider()
    event = provider.verify_renewal_webhook(payload, signature)
    original = db.get(BillingOrder, event.initial_order_id)
    if not original:
        raise HTTPException(404, 'Исходный заказ подписки не найден')
    lock_organization(db, original.organization_id)
    db.refresh(original)
    meta = json.loads(original.metadata_json)
    if (original.provider != provider.name or original.product_kind != 'subscription'
        or original.subscription_parent_id or not original.period_start or not original.period_end
        or original.status not in ('paid', 'refunded')
        or meta.get('subscription_reference') != event.subscription_reference
        or event.amount_rub != original.amount_rub or event.currency != original.currency):
        raise HTTPException(409, 'Продление не соответствует исходной подписке')
    start = cycle_boundary(aware(original.period_start), meta['billing_period'], event.cycle_number)
    end = cycle_boundary(aware(original.period_start), meta['billing_period'], event.cycle_number + 1)
    if (event.period_start != start or event.period_end != end
        or event.occurred_at > now() + timedelta(minutes=5)
        or event.occurred_at < aware(original.period_start)):
        raise HTTPException(409, 'Границы или дата оплаты периода не соответствуют подписке')
    digest = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
    receipt_id = 'renewal:' + hashlib.sha256(event.event_id.encode()).hexdigest()
    prior = db.query(CommerceWebhookEvent).filter_by(provider=provider.name, event_id=receipt_id).one_or_none()
    if prior:
        if prior.payload_hash != digest:
            raise HTTPException(409, 'Содержимое повторного уведомления изменилось')
        return json.loads(prior.response_json)
    key = hashlib.sha256(f'renewal:{original.id}:{event.cycle_number}'.encode()).hexdigest()
    order = db.query(BillingOrder).filter_by(organization_id=original.organization_id, idempotency_key=key).one_or_none()
    if order:
        if (order.subscription_parent_id != original.id or order.provider_reference != event.reference
            or order.amount_rub != event.amount_rub or aware(order.period_start) != start):
            raise HTTPException(409, 'Реквизиты расчётного периода изменились')
    else:
        cycle_meta = {key: meta[key] for key in ('billing_period', 'plan_snapshot', 'commercial_policy_version', 'subscription_reference')}
        cycle_meta['cycle_number'] = event.cycle_number
        order = BillingOrder(organization_id=original.organization_id, product_kind='subscription',
            product_code=original.product_code, amount_rub=original.amount_rub, currency=original.currency,
            provider=provider.name, provider_reference=event.reference, idempotency_key=key,
            subscription_parent_id=original.id, period_start=start, period_end=end,
            status='pending_payment', metadata_json=json.dumps(cycle_meta))
        db.add(order)
    try:
        db.flush()
        receipt = CommerceWebhookEvent(provider=provider.name, event_id=receipt_id,
            order_id=order.id, payload_hash=digest, response_json='{}')
        db.add(receipt)
        db.flush()  # Claim before applying money, also across different organizations.
    except IntegrityError:
        raise HTTPException(409, 'Платёж или событие уже связано с другим заказом') from None
    sub = get_subscription(db, original.organization_id)
    active_agreement = sub and sub.agreement_order_id == original.id
    cancellation = meta.get('renewal_cancel_effective_at')
    from datetime import datetime
    eligible = bool(active_agreement and original.status == 'paid'
        and not (cancellation and start >= datetime.fromisoformat(cancellation)))
    if order.status == 'refunded':
        pass  # A late paid/failed event cannot undo the refund.
    elif event.status == 'paid':
        if order.status == 'paid' and aware(order.paid_at) != event.occurred_at:
            raise HTTPException(409, 'Подтверждённая дата оплаты периода изменилась')
        if order.status != 'paid':
            order.status = 'paid'
            order.paid_at = event.occurred_at
            order.entitlement_eligible = eligible
            audit(db, actor_user_id=None, action='billing.paid', entity_type='billing_order', entity_id=order.id,
                payload={'organization_id': original.organization_id, 'amount_rub': order.amount_rub,
                    'provider': provider.name, 'renewal': True, 'requires_operator': not eligible})
    elif order.status not in ('paid', 'failed'):
        order.status = 'failed'
        audit(db, actor_user_id=None, action='billing.failed', entity_type='billing_order', entity_id=order.id,
            payload={'organization_id': original.organization_id, 'renewal': True})
    db.flush()
    sub = get_subscription(db, original.organization_id)
    if (active_agreement and eligible and order.status == 'failed'
        and start <= now() and aware(sub.current_period_end) <= now()):
        sub.status = 'past_due'
    result = {'order_id': order.id, 'status': order.status, 'test_mode': provider.test_mode,
        'requires_operator': order.status == 'paid' and not order.entitlement_eligible}
    receipt.response_json = json.dumps(result)
    audit(db, actor_user_id=None, action='subscription.renewal_received', entity_type='billing_order', entity_id=order.id,
        payload={'organization_id': original.organization_id, 'cycle_number': event.cycle_number,
            'period_start': start.isoformat(), 'period_end': end.isoformat(), 'status': order.status})
    db.flush()
    return result
