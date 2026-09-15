"""Commercial API: membership, billing roles, rate limits, audit and provider gates."""

import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import get_plan, plan_payload, seed_catalog, validate_features
from booker_api.commerce.entitlements import get_entitlements, get_subscription
from booker_api.commerce.orders import (
    create_subscription_order,
    lock_organization,
    order_payload,
    settle_event,
)
from booker_api.commerce.provider import (
    InvalidWebhook,
    ProviderUnavailable,
    get_provider,
    signed_test_event,
    stub_enabled,
)
from booker_api.commerce.service import (
    cancel_order,
    cancel_subscription,
    expire_subscriptions,
    schedule_change,
    subscription_payload,
)
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import (
    BillingOrder,
    CommercialPlan,
    Organization,
    PromotionProduct,
    Subscription,
    User,
)
from booker_api.rate_limit import analytics_limiter, client_key, messaging_limiter, webhook_limiter
from booker_api.security import audit, aware, current_user, now, require_admin, require_org_member


def commercial_gate(request: Request):
    if not settings.commercial_plans:
        raise HTTPException(404, "Коммерческие тарифы пока недоступны")
    analytics_limiter.check(client_key(request, "commerce"))


router = APIRouter(prefix="/commerce", tags=["commerce"], dependencies=[Depends(commercial_gate)])
admin_router = APIRouter(prefix="/admin/commerce", tags=["admin-commerce"])


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OrderInput(StrictInput):
    plan_code: str = Field(min_length=1, max_length=64)
    billing_period: Literal["monthly", "annual"] = "monthly"
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class PlanChange(StrictInput):
    plan_code: str = Field(min_length=1, max_length=64)


class PlanUpdate(StrictInput):
    expected_version: int = Field(ge=1)
    monthly_price_rub: int = Field(ge=0, le=10000000)
    annual_price_rub: int = Field(ge=0, le=100000000)
    supplier_fee_bps: int = Field(ge=0, le=10000)
    customer_fee_bps: int = Field(ge=0, le=10000)
    features: dict
    reason: str = Field(min_length=3, max_length=500)


class GrantInput(StrictInput):
    expected_updated_at: str | None = Field(default=None, max_length=64)
    plan_code: str = Field(min_length=1, max_length=64)
    status: Literal["active", "trial", "past_due", "cancelled", "expired"] = "active"
    days: int = Field(ge=1, le=366)
    reason: str = Field(min_length=3, max_length=500)


class StubComplete(StrictInput):
    status: Literal["paid", "failed"] = "paid"


def billing_writer(db: Session, user: User, org_id: str) -> None:
    member = require_org_member(db, user, org_id)
    if member.role not in {"owner", "admin"}:
        raise HTTPException(403, "Тарифом управляет владелец или администратор организации")
    messaging_limiter.check(f"billing:{user.id}")


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    seed_catalog(db)
    plans = (
        db.query(CommercialPlan)
        .filter_by(active=True)
        .order_by(CommercialPlan.audience, CommercialPlan.sort_order)
        .all()
    )
    products = db.query(PromotionProduct).filter_by(active=True).all()
    provider = get_provider()
    result = {
        "plans": [plan_payload(p) for p in plans],
        "promotions": [
            {
                "code": p.code,
                "audience": p.audience,
                "title": p.title,
                "price_rub": p.price_rub,
                "duration_hours": p.duration_hours,
                "version": p.version,
            }
            for p in products
        ],
        "checkout_available": provider.name != "disabled",
        "test_mode": provider.test_mode,
        "flags": {
            name.upper(): getattr(settings, name)
            for name in (
                "commercial_plans",
                "paid_promotion",
                "artist_growth",
                "opportunities",
                "smart_matching",
                "compatibility",
                "customer_business",
            )
        },
    }
    db.commit()
    return result


@router.get("/organizations/{org_id}")
def organization_commerce(
    org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    member = require_org_member(db, user, org_id)
    expire_subscriptions(db, org_id)
    result = {
        **get_entitlements(db, org_id),
        "subscription": subscription_payload(get_subscription(db, org_id)),
        "can_manage": member.role in {"owner", "admin"},
        "orders": [
            order_payload(o)
            for o in db.query(BillingOrder)
            .filter_by(organization_id=org_id)
            .order_by(BillingOrder.created_at.desc())
            .limit(100)
            .all()
        ],
    }
    db.commit()
    return result


@router.post("/organizations/{org_id}/orders")
def create_order(
    org_id: str, body: OrderInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    billing_writer(db, user, org_id)
    if body.plan_code == "customer_business" and not settings.customer_business:
        raise HTTPException(404, "Тариф Business пока недоступен")
    row = create_subscription_order(
        db, org_id, body.plan_code, body.billing_period, body.idempotency_key, user.id
    )
    db.commit()
    return order_payload(row)


@router.get("/orders/{order_id}")
def get_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.get(BillingOrder, order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    require_org_member(db, user, order.organization_id)
    return order_payload(order)


@router.post("/orders/{order_id}/cancel")
def post_cancel_order(
    order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    order = db.get(BillingOrder, order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    billing_writer(db, user, order.organization_id)
    cancel_order(db, order, user.id)
    db.commit()
    return order_payload(order)


@router.post("/organizations/{org_id}/subscription/cancel")
def post_cancel_subscription(
    org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    billing_writer(db, user, org_id)
    result = cancel_subscription(db, org_id, user.id)
    db.commit()
    return result


@router.post("/organizations/{org_id}/subscription/change")
def post_change_subscription(
    org_id: str, body: PlanChange, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    billing_writer(db, user, org_id)
    result = schedule_change(db, org_id, body.plan_code, user.id)
    db.commit()
    return result


@router.post("/webhook")
async def webhook(
    request: Request, x_commerce_signature: str = Header(default=""), db: Session = Depends(get_db)
):
    webhook_limiter.check(client_key(request, "commerce-webhook"))
    payload = await request.body()
    if len(payload) > 16384:
        raise HTTPException(413, "Уведомление слишком большое")
    try:
        result = settle_event(db, payload, x_commerce_signature)
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except InvalidWebhook as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return result


@router.post("/orders/{order_id}/test-complete")
def test_complete(
    order_id: str,
    body: StubComplete,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not stub_enabled():
        raise HTTPException(404, "Тестовая оплата недоступна")
    order = db.get(BillingOrder, order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    billing_writer(db, user, order.organization_id)
    if order.provider != "stub" or not order.provider_reference:
        raise HTTPException(409, "Заказ не относится к тестовому провайдеру")
    payload, signature = signed_test_event(
        order.id,
        order.provider_reference,
        order.amount_rub,
        body.status,
        f"test:{order.id}:{body.status}",
    )
    result = settle_event(db, payload, signature)
    db.commit()
    return result


@admin_router.get("/catalog")
def admin_catalog(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return catalog(db)


@admin_router.put("/plans/{code}")
def update_plan(
    code: str, body: PlanUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    messaging_limiter.check(f"admin-commerce:{user.id}")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Укажите содержательную причину изменения")
    validate_features(body.features)
    plan = get_plan(db, code)
    # Free remains usable, regardless of an accidental admin edit.
    if plan.sort_order == 0:
        if body.monthly_price_rub or body.annual_price_rub:
            raise HTTPException(422, "Базовый тариф должен оставаться бесплатным")
        base = json.loads(plan.features_json)
        for key in ("analytics.basic", "opportunities.access"):
            if base.get(key) and body.features.get(key) is not True:
                raise HTTPException(422, "Базовые возможности Free нельзя отключать")
    changed = db.execute(
        update(CommercialPlan)
        .where(
            CommercialPlan.id == plan.id,
            CommercialPlan.version == body.expected_version,
            CommercialPlan.active.is_(True),
        )
        .values(active=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Тариф уже изменился. Обновите страницу")
    old_payload = plan_payload(plan)
    newer = CommercialPlan(
        code=plan.code,
        audience=plan.audience,
        title=plan.title,
        sort_order=plan.sort_order,
        version=plan.version + 1,
        monthly_price_rub=body.monthly_price_rub,
        annual_price_rub=body.annual_price_rub,
        supplier_fee_bps=body.supplier_fee_bps,
        customer_fee_bps=body.customer_fee_bps,
        features_json=json.dumps(body.features),
        active=True,
    )
    db.add(newer)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="commercial.plan_changed",
        entity_type="commercial_plan",
        entity_id=newer.id,
        payload={"before": old_payload, "after": plan_payload(newer), "reason": body.reason},
    )
    db.commit()
    return plan_payload(newer)


@admin_router.post("/organizations/{org_id}/grant")
def grant_plan(
    org_id: str,
    body: GrantInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    messaging_limiter.check(f"admin-commerce:{user.id}")
    lock_organization(db, org_id)
    org = db.get(Organization, org_id)
    plan = get_plan(db, body.plan_code)
    if plan.audience != org.kind:
        raise HTTPException(422, "Тариф не подходит типу организации")
    sub = get_subscription(db, org_id)
    _check_subscription_version(sub, body.expected_updated_at)
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Укажите содержательную причину изменения")
    if sub and sub.provider_subscription_id:
        raise HTTPException(409, "Сначала отмените автопродление действующей подписки")
    if sub is None:
        sub = Subscription(organization_id=org_id)
        db.add(sub)
    sub.plan_code = plan.code
    sub.status = body.status
    sub.billing_period = "manual"
    sub.provider = "manual"
    sub.starts_at = now()
    sub.current_period_end = now() + timedelta(days=body.days)
    sub.cancel_at_period_end = False
    sub.next_plan_code = None
    sub.last_billing_order_id = None
    audit(
        db,
        actor_user_id=user.id,
        action="subscription.admin_grant",
        entity_type="organization",
        entity_id=org_id,
        payload={
            "plan_code": plan.code,
            "status": body.status,
            "days": body.days,
            "reason": body.reason,
        },
    )
    db.commit()
    return subscription_payload(sub)


class CampaignInput(StrictInput):
    target_type: Literal["artist", "venue"]
    target_id: str = Field(min_length=1, max_length=36)
    product_code: Literal["BOOST_24H", "BOOST_72H", "BOOST_7D", "FEATURED_7D"]
    use_credit: bool = False
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class TouchInput(StrictInput):
    action: Literal["impression", "click"]


@router.post("/organizations/{org_id}/promotions")
def post_promotion(
    org_id: str,
    body: CampaignInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from booker_api.commerce.promotions import campaign_payload, create_campaign

    billing_writer(db, user, org_id)
    if not settings.paid_promotion:
        raise HTTPException(404, "Продвижение пока недоступно")
    campaign = create_campaign(db, org_id, body.model_dump(), user.id)
    db.commit()
    return campaign_payload(db, campaign)


@router.get("/organizations/{org_id}/promotions")
def get_promotions(org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from booker_api.commerce.promotions import campaign_payload, credits_summary, expire_campaigns
    from booker_api.models import Artist, PromotionCampaign, Venue

    require_org_member(db, user, org_id)
    if not settings.paid_promotion:
        raise HTTPException(404, "Продвижение пока недоступно")
    expire_campaigns(db, org_id)
    campaigns = (
        db.query(PromotionCampaign)
        .filter_by(organization_id=org_id)
        .order_by(PromotionCampaign.created_at.desc())
        .limit(100)
        .all()
    )
    targets = [
        {"id": a.id, "name": a.name, "type": "artist"}
        for a in db.query(Artist).filter_by(organization_id=org_id)
    ]
    targets += [
        {"id": v.id, "name": v.name, "type": "venue"}
        for v in db.query(Venue).filter_by(organization_id=org_id)
    ]
    result = {
        "items": [campaign_payload(db, c) for c in campaigns],
        "credits": credits_summary(db, org_id),
        "targets": targets,
    }
    db.commit()
    return result


@router.post("/promotions/{campaign_id}/cancel")
def post_cancel_campaign(
    campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from booker_api.commerce.promotions import campaign_payload
    from booker_api.models import PromotionCampaign

    campaign = db.get(PromotionCampaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Кампания не найдена")
    billing_writer(db, user, campaign.organization_id)
    lock_organization(db, campaign.organization_id)
    if campaign.status not in {"cancelled", "expired", "rejected"}:
        order = (
            db.get(BillingOrder, campaign.billing_order_id) if campaign.billing_order_id else None
        )
        if order and order.status in {"created", "pending_payment", "failed"}:
            cancel_order(db, order, user.id)
        else:
            campaign.status = "cancelled"
            audit(
                db,
                actor_user_id=user.id,
                action="promotion.cancelled",
                entity_type="promotion",
                entity_id=campaign.id,
                payload={"organization_id": campaign.organization_id},
            )
    db.commit()
    return campaign_payload(db, campaign)


@router.post("/promotion-touches/{touch_id}")
def post_promotion_touch(
    touch_id: str, body: TouchInput, request: Request, db: Session = Depends(get_db)
):
    from booker_api.commerce.promotions import record_touch

    if not settings.paid_promotion:
        raise HTTPException(404, "Продвижение пока недоступно")
    messaging_limiter.check(client_key(request, "promotion-touch"))
    record_touch(db, touch_id, body.action)
    db.commit()
    return {"ok": True}


class PromotionPriceUpdate(StrictInput):
    expected_version: int = Field(strict=True, ge=1)
    price_rub: int = Field(strict=True, ge=1, le=1_000_000)
    reason: str = Field(min_length=5, max_length=500)


@admin_router.put("/promotions/{audience}/{code}")
def update_promotion_price(
    audience: Literal["artist", "venue"],
    code: str,
    body: PromotionPriceUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    messaging_limiter.check(f"admin-commerce:{user.id}")
    seed_catalog(db)
    product = (
        db.query(PromotionProduct)
        .filter_by(audience=audience, code=code, active=True)
        .order_by(PromotionProduct.version.desc())
        .first()
    )
    if not product:
        raise HTTPException(404, "Продукт продвижения не найден")
    changed = db.execute(
        update(PromotionProduct)
        .where(
            PromotionProduct.id == product.id,
            PromotionProduct.version == body.expected_version,
            PromotionProduct.active.is_(True),
        )
        .values(active=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Цена уже изменилась. Обновите страницу")
    newer = PromotionProduct(
        audience=audience,
        code=code,
        title=product.title,
        duration_hours=product.duration_hours,
        price_rub=body.price_rub,
        version=product.version + 1,
        active=True,
    )
    db.add(newer)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="commercial.promotion_price_changed",
        entity_type="promotion_product",
        entity_id=newer.id,
        payload={
            "audience": audience,
            "code": code,
            "before_price_rub": product.price_rub,
            "after_price_rub": newer.price_rub,
            "version": newer.version,
            "reason": body.reason,
        },
    )
    db.commit()
    return {
        "code": code,
        "audience": audience,
        "price_rub": newer.price_rub,
        "version": newer.version,
    }


class RevokeInput(StrictInput):
    expected_updated_at: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


def _check_subscription_version(sub, expected):
    if expected is not None and expected != (aware(sub.updated_at).isoformat() if sub else ''):
        raise HTTPException(409, 'Подписка изменилась. Обновите данные перед действием')


@admin_router.get('/organizations')
def commercial_organizations(q: str = Query(default='', max_length=128), limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000), user: User = Depends(require_admin), db: Session = Depends(get_db)):
    analytics_limiter.check(f'admin-commerce-list:{user.id}')
    query = db.query(Organization)
    if q.strip():
        query = query.filter((Organization.id == q.strip()) | Organization.name.contains(q.strip(), autoescape=True))
    total = query.count()
    rows = query.order_by(Organization.name, Organization.id).offset(offset).limit(limit).all()
    subs = {s.organization_id: s for s in db.query(Subscription).filter(Subscription.organization_id.in_([o.id for o in rows])).all()}
    return {'total': total, 'offset': offset, 'items': [{'id': org.id, 'name': org.name, 'kind': org.kind,
        'subscription': subscription_payload(subs.get(org.id)),
        'effective_status': ('expired' if subs[org.id].status in {'active', 'trial', 'past_due'} and aware(subs[org.id].current_period_end) <= now() else subs[org.id].status) if org.id in subs else 'free'} for org in rows]}


@admin_router.post('/organizations/{org_id}/revoke')
def revoke_plan(org_id: str, body: RevokeInput, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    messaging_limiter.check(f'admin-commerce:{user.id}')
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, 'Укажите содержательную причину отзыва')
    lock_organization(db, org_id)
    sub = get_subscription(db, org_id)
    if not sub:
        raise HTTPException(404, 'Подписка не найдена')
    _check_subscription_version(sub, body.expected_updated_at)
    if sub.provider_subscription_id:
        raise HTTPException(409, 'Сначала отключите автопродление у платёжного провайдера')
    if sub.status in {'cancelled', 'expired'}:
        return subscription_payload(sub)
    before = subscription_payload(sub)
    sub.status = 'cancelled'
    sub.current_period_end = now()
    sub.cancel_at_period_end = False
    sub.next_plan_code = None
    audit(db, actor_user_id=user.id, action='subscription.admin_revoke', entity_type='organization', entity_id=org_id,
        payload={'plan_code': sub.plan_code, 'previous_status': before['status'], 'reason': body.reason.strip(), 'refund_created': False})
    db.commit()
    return subscription_payload(sub)
