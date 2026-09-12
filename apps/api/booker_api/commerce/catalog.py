"""Versioned server catalog. Prices are RUB, rates are integer basis points."""

import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.models import CommercialPlan, PromotionProduct

POLICY_VERSION = "commercial-v3-2026-09-12"
FEATURES = {
    "analytics.basic": "Базовая аналитика",
    "analytics.advanced": "Расширенная аналитика и причины потерь",
    "analytics.benchmark": "Обезличенное сравнение с похожими профилями",
    "analytics.days": "Глубина аналитики, дней",
    "opportunities.access": "Подходящие заказы и отклики",
    "opportunities.filters": "Расширенные фильтры заказов",
    "opportunities.instant_alerts": "Мгновенные уведомления о заказах",
    "portfolio.advanced": "Расширенное портфолио и настройки витрины",
    "geography.advanced": "Расширенная география",
    "promotion.monthly_credits": "Boost на 24 часа в месяц",
    "promotion.featured_access": "Доступ к Featured",
    "team.seats": "Участников команды",
    "export.analytics": "Экспорт статистики",
    "support.priority": "Приоритетная поддержка",
    "customer.templates": "Шаблоны мероприятий",
    "customer.multi_user": "Совместная работа команды",
    "customer.analytics": "Аналитика мероприятий",
    "customer.notes": "Внутренние комментарии",
    "customer.supplier_history": "История поставщиков",
    "customer.exports": "Экспорт документов",
}
NUMERIC_FEATURES = {"analytics.days", "promotion.monthly_credits", "team.seats"}
FREE_FEATURES = {
    "analytics.basic": True,
    "analytics.days": 30,
    "opportunities.access": True,
    "promotion.monthly_credits": 0,
    "team.seats": 1,
}
PRO_FEATURES = {
    **FREE_FEATURES,
    "analytics.advanced": True,
    "analytics.days": 90,
    "opportunities.filters": True,
    "opportunities.instant_alerts": True,
    "portfolio.advanced": True,
    "geography.advanced": True,
    "promotion.monthly_credits": 2,
    "team.seats": 2,
}
PREMIUM_FEATURES = {
    **PRO_FEATURES,
    "analytics.days": 365,
    "analytics.benchmark": True,
    "promotion.monthly_credits": 8,
    "promotion.featured_access": True,
    "team.seats": 5,
    "export.analytics": True,
    "support.priority": True,
}
BUSINESS_FEATURES = {
    "team.seats": 5,
    "customer.templates": True,
    "customer.multi_user": True,
    "customer.analytics": True,
    "customer.notes": True,
    "customer.supplier_history": True,
    "customer.exports": True,
    "support.priority": True,
}
PLAN_DEFAULTS = (
    ("artist_free", "artist", "Free", 0, 0, 400, FREE_FEATURES, 0),
    ("artist_pro", "artist", "Pro", 1990, 19900, 300, PRO_FEATURES, 1),
    ("artist_premium", "artist", "Premium", 4990, 49900, 200, PREMIUM_FEATURES, 2),
    ("venue_free", "venue", "Free", 0, 0, 400, FREE_FEATURES, 0),
    ("venue_pro", "venue", "Pro", 3990, 39900, 300, PRO_FEATURES, 1),
    ("venue_premium", "venue", "Premium", 7990, 79900, 200, PREMIUM_FEATURES, 2),
    ("customer_standard", "customer", "Standard", 0, 0, 0, {"team.seats": 1}, 0),
    ("customer_business", "customer", "Business", 4990, 49900, 0, BUSINESS_FEATURES, 1),
)
PROMOTION_DEFAULTS = (
    ("BOOST_24H", "Boost на 24 часа", 24, 490, 990),
    ("BOOST_72H", "Boost на 3 дня", 72, 990, 1990),
    ("BOOST_7D", "Boost на 7 дней", 168, 1990, 3990),
    ("FEATURED_7D", "Featured на 7 дней", 168, 4990, 9990),
)


def seed_catalog(db: Session) -> None:
    """Idempotent seed, never reset an administrator's existing revisions."""
    for code, audience, title, monthly, annual, bps, features, sort in PLAN_DEFAULTS:
        if db.query(CommercialPlan.id).filter_by(code=code).first():
            continue
        try:
            with db.begin_nested():
                db.add(
                    CommercialPlan(
                        code=code,
                        audience=audience,
                        title=title,
                        monthly_price_rub=monthly,
                        annual_price_rub=annual,
                        supplier_fee_bps=bps,
                        customer_fee_bps=600,
                        features_json=json.dumps(features),
                        sort_order=sort,
                        version=1,
                    )
                )
                db.flush()
        except IntegrityError:
            # A concurrent startup seeded the same immutable revision.
            pass
    for code, title, hours, artist_price, venue_price in PROMOTION_DEFAULTS:
        for audience, price in (("artist", artist_price), ("venue", venue_price)):
            if db.query(PromotionProduct.id).filter_by(code=code, audience=audience).first():
                continue
            try:
                with db.begin_nested():
                    db.add(
                        PromotionProduct(
                            audience=audience,
                            code=code,
                            title=title,
                            price_rub=price,
                            duration_hours=hours,
                            version=1,
                        )
                    )
                    db.flush()
            except IntegrityError:
                pass


def get_plan(db: Session, code: str) -> CommercialPlan:
    seed_catalog(db)
    plan = (
        db.query(CommercialPlan)
        .filter_by(code=code, active=True)
        .order_by(CommercialPlan.version.desc())
        .first()
    )
    if not plan:
        raise HTTPException(404, "Тариф недоступен")
    return plan


def free_code(audience: str) -> str:
    return "customer_standard" if audience == "customer" else f"{audience}_free"


def policy_version(plan: CommercialPlan, customer_plan: CommercialPlan | None = None) -> str:
    version = f"{POLICY_VERSION}:{plan.code}@{plan.version}"
    return (
        version
        if customer_plan is None
        else f"{version}:{customer_plan.code}@{customer_plan.version}"
    )


def plan_payload(plan: CommercialPlan) -> dict:
    features = json.loads(plan.features_json)
    return {
        "code": plan.code,
        "audience": plan.audience,
        "title": plan.title,
        "monthly_price_rub": plan.monthly_price_rub,
        "annual_price_rub": plan.annual_price_rub,
        "annual_savings_rub": max(0, plan.monthly_price_rub * 12 - plan.annual_price_rub),
        "supplier_fee_bps": plan.supplier_fee_bps,
        "customer_fee_bps": plan.customer_fee_bps,
        "features": features,
        "feature_labels": FEATURES,
        "version": plan.version,
        "commercial_policy_version": policy_version(plan),
        "currency": "RUB",
        "sort_order": plan.sort_order,
    }


def validate_features(features: dict) -> None:
    for code, value in features.items():
        if code not in FEATURES:
            raise HTTPException(422, "Неизвестная возможность тарифа")
        if code in NUMERIC_FEATURES:
            if type(value) is not int or not 0 <= value <= 1000:
                raise HTTPException(422, "Лимит должен быть целым числом от 0 до 1000")
        elif type(value) is not bool:
            raise HTTPException(422, "Доступ к возможности должен быть логическим значением")
