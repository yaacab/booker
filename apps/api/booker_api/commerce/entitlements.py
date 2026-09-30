"""One resolver for all paid capabilities. Expired grants never authorize access."""

import json

from fastapi import HTTPException
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import free_code, get_plan, plan_payload
from booker_api.config import settings
from booker_api.models import BillingOrder, CommercialPlan, Organization, Subscription
from booker_api.security import aware, now


def get_subscription(db: Session, organization_id: str) -> Subscription | None:
    sub = db.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
    if not sub or not sub.agreement_order_id:
        return sub
    # Paid future cycles become usable at their actual start, including after
    # delayed delivery or a process restart. Never grant an unpaid gap.
    instant = now()
    period = db.query(BillingOrder).filter(
        BillingOrder.organization_id == organization_id,
        or_(BillingOrder.id == sub.agreement_order_id,
            BillingOrder.subscription_parent_id == sub.agreement_order_id),
        BillingOrder.status == 'paid', BillingOrder.entitlement_eligible.is_(True),
        BillingOrder.period_start <= instant, BillingOrder.period_end > instant,
    ).order_by(BillingOrder.period_start.desc()).first()
    if period and (sub.last_billing_order_id != period.id or sub.status != 'active'):
        # Compare-and-set protects a concurrent upgrade/manual change. This is a
        # projection of persisted paid periods, never a payment or provider call.
        db.execute(update(Subscription).where(Subscription.id == sub.id,
            Subscription.agreement_order_id == sub.agreement_order_id,
            Subscription.last_billing_order_id == sub.last_billing_order_id,
            Subscription.status == sub.status).values(
                starts_at=period.period_start, current_period_end=period.period_end,
                last_billing_order_id=period.id, status='active').execution_options(synchronize_session=False))
        db.refresh(sub)
    return sub


def resolve_plan(db: Session, organization_id: str) -> CommercialPlan:
    org = db.get(Organization, organization_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    sub = get_subscription(db, organization_id)
    if (
        settings.commercial_plans
        and sub
        and sub.status in {"active", "trial"}
        and aware(sub.starts_at) <= now() < aware(sub.current_period_end)
    ):
        plan = get_plan(db, sub.plan_code)
        if plan.audience == org.kind:
            return plan
    return get_plan(db, free_code(org.kind))


def get_entitlements(db: Session, organization_id: str) -> dict:
    plan = resolve_plan(db, organization_id)
    features = json.loads(plan.features_json)
    if not settings.customer_business:
        features = {k: v for k, v in features.items() if not k.startswith("customer.")}
    return {"plan": plan_payload(plan), "features": features}


def require_feature(db: Session, organization_id: str, feature: str) -> None:
    if not get_entitlements(db, organization_id)["features"].get(feature, False):
        raise HTTPException(403, "Эта возможность доступна на расширенном тарифе")
