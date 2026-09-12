"""One resolver for all paid capabilities. Expired grants never authorize access."""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import free_code, get_plan, plan_payload
from booker_api.config import settings
from booker_api.models import CommercialPlan, Organization, Subscription
from booker_api.security import aware, now


def get_subscription(db: Session, organization_id: str) -> Subscription | None:
    return db.query(Subscription).filter_by(organization_id=organization_id).one_or_none()


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
