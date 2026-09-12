"""Paid insertion happens only after ordinary filtering, never instead of it."""

import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.commerce.catalog import seed_catalog
from booker_api.commerce.entitlements import get_entitlements, require_feature
from booker_api.commerce.orders import lock_organization, order_payload
from booker_api.commerce.provider import ProviderUnavailable, get_provider
from booker_api.config import settings
from booker_api.models import (
    Artist,
    BillingOrder,
    Booking,
    Event,
    Offer,
    PromotionCampaign,
    PromotionCreditUse,
    PromotionProduct,
    PromotionTouch,
    Request,
    TeamMember,
    Venue,
    VenueHall,
)
from booker_api.security import audit, aware, now


def promotion_target(db: Session, org_id: str, target_type: str, target_id: str):
    target = db.get(Artist if target_type == "artist" else Venue, target_id)
    if not target or target.organization_id != org_id:
        raise HTTPException(403, "Можно продвигать только профиль своей организации")
    if target_type == "venue" and (
        target.moderation_status != "published"
        or target.availability_mode != "owner"
        or not target.is_claimed
    ):
        raise HTTPException(422, "Для продвижения подтвердите профиль и календарь площадки")
    return target


def credits_summary(db: Session, org_id: str) -> dict:
    included = int(get_entitlements(db, org_id)["features"].get("promotion.monthly_credits", 0))
    period = now().strftime("%Y-%m")
    used = db.query(PromotionCreditUse).filter_by(organization_id=org_id, period_key=period).count()
    return {
        "period": period,
        "included": included,
        "used": used,
        "remaining": max(0, included - used),
    }


def create_campaign(db: Session, org_id: str, data: dict, actor_id: str) -> PromotionCampaign:
    lock_organization(db, org_id)
    seed_catalog(db)
    target = promotion_target(db, org_id, data["target_type"], data["target_id"])
    # Both purchase methods share one semantic idempotency scope.
    credit = (
        db.query(PromotionCreditUse)
        .filter_by(organization_id=org_id, idempotency_key=data["idempotency_key"])
        .one_or_none()
    )
    order = (
        db.query(BillingOrder)
        .filter_by(organization_id=org_id, idempotency_key=data["idempotency_key"])
        .one_or_none()
    )
    existing = (
        db.get(PromotionCampaign, credit.campaign_id)
        if credit
        else (
            db.query(PromotionCampaign).filter_by(billing_order_id=order.id).one_or_none()
            if order
            else None
        )
    )
    if credit or order:
        if (
            not existing
            or existing.target_id != target.id
            or existing.target_type != data["target_type"]
            or existing.product_code != data["product_code"]
            or bool(credit) != data["use_credit"]
        ):
            raise HTTPException(409, "Этот ключ уже использован для другого заказа")
        return existing
    product = (
        db.query(PromotionProduct)
        .filter_by(audience=data["target_type"], code=data["product_code"], active=True)
        .order_by(PromotionProduct.version.desc())
        .first()
    )
    if not product:
        raise HTTPException(404, "Продукт продвижения недоступен")
    if product.code == "FEATURED_7D":
        require_feature(db, org_id, "promotion.featured_access")
    if data["use_credit"]:
        if product.code != "BOOST_24H":
            raise HTTPException(422, "Включённый Boost действует 24 часа")
        if credits_summary(db, org_id)["remaining"] < 1:
            raise HTTPException(409, "В этом месяце не осталось включённых Boost")
    start = now()
    campaign = PromotionCampaign(
        organization_id=org_id,
        target_type=data["target_type"],
        target_id=target.id,
        product_code=product.code,
        city=target.city,
        category=target.category if data["target_type"] == "artist" else "venue",
        starts_at=start,
        ends_at=start + timedelta(hours=product.duration_hours),
        status="active" if data["use_credit"] else "pending_payment",
    )
    if not data["use_credit"]:
        provider = get_provider()
        meta = {
            "duration_hours": product.duration_hours,
            "target_id": target.id,
            "target_type": data["target_type"],
            "product_title": product.title,
            "commercial_policy_version": f"promotion:{product.audience}:{product.code}@{product.version}",
        }
        order = BillingOrder(
            organization_id=org_id,
            product_kind="promotion",
            product_code=product.code,
            amount_rub=product.price_rub,
            provider=provider.name,
            idempotency_key=data["idempotency_key"],
            metadata_json=json.dumps(meta),
        )
        db.add(order)
        db.flush()
        try:
            checkout = provider.create_checkout(
                order_id=order.id,
                amount_rub=order.amount_rub,
                currency="RUB",
                idempotency_key=order.id,
            )
            order.provider_reference = checkout.reference
            order.status = "pending_payment"
            meta["checkout_url"] = checkout.url
        except ProviderUnavailable:
            order.status = "created"
        order.metadata_json = json.dumps(meta)
        campaign.billing_order_id = order.id
    db.add(campaign)
    db.flush()
    if data["use_credit"]:
        db.add(
            PromotionCreditUse(
                organization_id=org_id,
                campaign_id=campaign.id,
                period_key=start.strftime("%Y-%m"),
                idempotency_key=data["idempotency_key"],
            )
        )
        audit(
            db,
            actor_user_id=actor_id,
            action="promotion.started",
            entity_type="promotion",
            entity_id=campaign.id,
            payload={"source": "included_credit", "organization_id": org_id},
        )
    audit(
        db,
        actor_user_id=actor_id,
        action="promotion.created",
        entity_type="promotion",
        entity_id=campaign.id,
        payload={
            "organization_id": org_id,
            "product_code": product.code,
            "target_id": target.id,
            "target_type": data["target_type"],
        },
    )
    return campaign


def settle_campaign(db: Session, order: BillingOrder) -> None:
    campaign = db.query(PromotionCampaign).filter_by(billing_order_id=order.id).one_or_none()
    if not campaign:
        raise HTTPException(409, "Кампания заказа не найдена")
    if order.status == "paid":
        if campaign.status != "pending_payment":
            raise HTTPException(409, "Кампания не ожидает оплаты")
        try:
            promotion_target(db, campaign.organization_id, campaign.target_type, campaign.target_id)
        except HTTPException:
            campaign.status = "rejected"
            audit(
                db,
                actor_user_id=None,
                action="promotion.rejected",
                entity_type="promotion",
                entity_id=campaign.id,
                payload={"reason": "profile_no_longer_eligible", "refund_required": True},
            )
            return
        meta = json.loads(order.metadata_json)
        campaign.starts_at = now()
        campaign.ends_at = now() + timedelta(hours=meta["duration_hours"])
        campaign.status = "active"
        audit(
            db,
            actor_user_id=None,
            action="promotion.started",
            entity_type="promotion",
            entity_id=campaign.id,
            payload={"billing_order_id": order.id},
        )
    elif order.status in {"refunded", "cancelled", "failed"}:
        campaign.status = "cancelled"
        audit(
            db,
            actor_user_id=None,
            action="promotion.cancelled",
            entity_type="promotion",
            entity_id=campaign.id,
            payload={"billing_order_id": order.id, "payment_status": order.status},
        )


def expire_campaigns(db: Session, org_id: str | None = None) -> None:
    query = db.query(PromotionCampaign).filter(
        PromotionCampaign.status.in_(["active", "scheduled"]), PromotionCampaign.ends_at <= now()
    )
    if org_id:
        query = query.filter_by(organization_id=org_id)
    for campaign in query.all():
        updated = db.execute(
            update(PromotionCampaign)
            .where(PromotionCampaign.id == campaign.id, PromotionCampaign.status == campaign.status)
            .values(status="expired")
        )
        if updated.rowcount:
            audit(
                db,
                actor_user_id=None,
                action="promotion.expired",
                entity_type="promotion",
                entity_id=campaign.id,
            )


def insert_sponsored(db: Session, items: list[dict], target_type: str) -> list[dict]:
    """No candidate lookup can append an ineligible profile to the filtered results."""
    for rank, item in enumerate(items):
        item.update(organic_rank=rank, sponsored=False)
    if not settings.paid_promotion or len(items) < 5:
        return items
    expire_campaigns(db)
    eligible = {
        item["id"]: item for item in items if item.get("availability_mode", "owner") == "owner"
    }
    campaigns = (
        db.query(PromotionCampaign)
        .filter(
            PromotionCampaign.target_type == target_type,
            PromotionCampaign.status == "active",
            PromotionCampaign.starts_at <= now(),
            PromotionCampaign.ends_at > now(),
            PromotionCampaign.target_id.in_(list(eligible)),
        )
        .order_by(PromotionCampaign.starts_at, PromotionCampaign.id)
        .all()
    )
    selected = []
    used = set()
    for campaign in campaigns:
        item = eligible[campaign.target_id]
        if campaign.target_id in used or (campaign.city and campaign.city != item["city"]):
            continue
        if campaign.category and campaign.category != item.get("category"):
            continue
        try:
            promotion_target(db, campaign.organization_id, target_type, campaign.target_id)
        except HTTPException:
            continue
        touch = PromotionTouch(campaign_id=campaign.id, expires_at=now() + timedelta(days=7))
        db.add(touch)
        db.flush()
        item.update(
            sponsored=True,
            sponsored_label="Продвижение",
            promotion_campaign_id=campaign.id,
            promotion_touch_id=touch.id,
        )
        selected.append(item)
        used.add(item["id"])
        if len(selected) == len(items) // 5:
            break
    organic = iter(item for item in items if item["id"] not in used)
    sponsored = iter(selected)
    output = []
    for pos in range(len(items)):
        if pos % 5 == 1 and pos // 5 < len(selected):
            output.append(next(sponsored))
        else:
            output.append(next(organic))
    return output


def record_touch(db: Session, touch_id: str, action: str) -> None:
    touch = db.get(PromotionTouch, touch_id)
    if not touch or aware(touch.expires_at) <= now():
        raise HTTPException(404, "Переход недоступен")
    if action == "click" and touch.impressed_at is None:
        record_touch(db, touch_id, "impression")
    column = PromotionTouch.impressed_at if action == "impression" else PromotionTouch.clicked_at
    changed = db.execute(
        update(PromotionTouch)
        .where(PromotionTouch.id == touch_id, column.is_(None))
        .values({column.key: now()})
    )
    if changed.rowcount:
        audit(
            db,
            actor_user_id=None,
            action=f"promotion.{action}",
            entity_type="promotion",
            entity_id=touch.campaign_id,
            payload={"touch_id": touch.id},
        )


def attribute_request(db: Session, req: Request, touch_id: str | None, actor_id: str) -> None:
    if not touch_id:
        return
    touch = db.get(PromotionTouch, touch_id)
    if not touch or not touch.clicked_at or touch.request_id or aware(touch.expires_at) <= now():
        return
    campaign = db.get(PromotionCampaign, touch.campaign_id)
    resource_id = req.resource_id
    resource_type = req.resource_type
    if resource_type == "hall":
        hall = db.get(VenueHall, resource_id)
        resource_id = hall.venue_id if hall else None
        resource_type = "venue"
    if campaign.target_id != resource_id or campaign.target_type != resource_type:
        return
    # Supply cannot inflate attributed conversions with its own team accounts.
    if (
        db.query(TeamMember.id)
        .filter_by(user_id=actor_id, organization_id=campaign.organization_id)
        .first()
    ):
        return
    event = db.get(Event, req.event_id)
    updated = db.execute(
        update(PromotionTouch)
        .where(PromotionTouch.id == touch.id, PromotionTouch.request_id.is_(None))
        .values(request_id=req.id, customer_org_id=event.organization_id)
    )
    if updated.rowcount:
        audit(
            db,
            actor_user_id=actor_id,
            action="promotion.request",
            entity_type="promotion",
            entity_id=campaign.id,
            payload={"request_id": req.id, "touch_id": touch.id},
        )


def attribute_booking(db: Session, booking: Booking) -> None:
    offer = db.get(Offer, booking.offer_id)
    touch = db.query(PromotionTouch).filter_by(request_id=offer.request_id).one_or_none()
    if not touch:
        return
    updated = db.execute(
        update(PromotionTouch)
        .where(PromotionTouch.id == touch.id, PromotionTouch.booking_id.is_(None))
        .values(booking_id=booking.id)
    )
    if updated.rowcount:
        audit(
            db,
            actor_user_id=None,
            action="promotion.booking",
            entity_type="promotion",
            entity_id=touch.campaign_id,
            payload={"booking_id": booking.id, "request_id": offer.request_id},
        )


def campaign_payload(db: Session, campaign: PromotionCampaign) -> dict:
    touches = db.query(PromotionTouch).filter_by(campaign_id=campaign.id).all()
    impressions = sum(t.impressed_at is not None for t in touches)
    clicks = sum(t.clicked_at is not None for t in touches)
    order = db.get(BillingOrder, campaign.billing_order_id) if campaign.billing_order_id else None
    return {
        "id": campaign.id,
        "target_type": campaign.target_type,
        "target_id": campaign.target_id,
        "product_code": campaign.product_code,
        "status": campaign.status,
        "starts_at": aware(campaign.starts_at),
        "ends_at": aware(campaign.ends_at),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(clicks / impressions, 4) if impressions else None,
        "requests": sum(t.request_id is not None for t in touches),
        "bookings": sum(t.booking_id is not None for t in touches),
        "order": order_payload(order) if order else None,
    }
