import hashlib
import json
from collections import Counter
from datetime import timedelta
from statistics import median

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.calendar import MSK, open_slots_unmasked
from booker_api.commerce.entitlements import get_entitlements
from booker_api.config import settings
from booker_api.models import (
    Artist,
    AuditLog,
    AvailabilitySlot,
    Booking,
    BookingHold,
    DiscoverySignal,
    Offer,
    OfferVersion,
    Organization,
    Request,
    Venue,
    VenueHall,
)
from booker_api.security import audit, aware, membership, now

LOSS_LABELS = {
    "customer_selected_another": "Заказчик выбрал другого",
    "request_expired": "Заявка истекла",
    "offer_expired": "Предложение истекло",
    "event_cancelled": "Событие отменено",
    "supplier_declined": "Исполнитель отказался",
    "price": "Заказчик отметил цену",
    "unknown": "Причина не указана",
}


def target(db: Session, kind: str, target_id: str):
    row = db.get(Artist if kind == "artist" else Venue, target_id)
    if not row or (kind == "venue" and row.moderation_status != "published"):
        raise HTTPException(404, "Профиль не найден")
    return row


def record_signal(db: Session, kind: str, target_id: str, signal: str, visitor: str, actor_id=None):
    if not settings.artist_growth:
        return
    profile = target(db, kind, target_id)
    if actor_id and membership(db, actor_id, profile.organization_id):
        return
    visitor_key = hashlib.sha256(visitor.encode()).hexdigest()
    row = DiscoverySignal(
        organization_id=profile.organization_id,
        target_type=kind,
        target_id=target_id,
        kind=signal,
        visitor_key=visitor_key,
        day_key=now().date().isoformat(),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
            audit(
                db,
                actor_user_id=actor_id,
                action=f"discovery.{signal}",
                entity_type=kind,
                entity_id=target_id,
                payload={"organization_id": profile.organization_id, "signal_id": row.id},
            )
    except IntegrityError:
        # A repeated view or concurrent retry is one daily observation.
        pass


def profile_request_filter(db, kind, target_id):
    direct = and_(Request.resource_type == kind, Request.resource_id == target_id)
    if kind == "venue":
        halls = db.query(VenueHall.id).filter_by(venue_id=target_id)
        return or_(direct, and_(Request.resource_type == "hall", Request.resource_id.in_(halls)))
    return direct


def response_stats(db: Session, kind: str, target_id: str, days=90):
    observations = (
        db.query(Request.created_at, func.min(Offer.created_at))
        .join(Offer, Offer.request_id == Request.id)
        .filter(
            profile_request_filter(db, kind, target_id),
            Request.created_at >= now() - timedelta(days=days),
        )
        .group_by(Request.id)
        .all()
    )
    seconds = [
        max(0, int((aware(end) - aware(start)).total_seconds())) for start, end in observations
    ]
    value = int(median(seconds)) if seconds else None
    return {
        "median_seconds": value,
        "sample_size": len(seconds),
        "days": days,
        "label": "Пока недостаточно ответов для расчёта"
        if value is None
        else f"Первое предложение: обычно за {max(1, round(value / 60))} мин",
    }


def profile_requests(db, profile):
    kind = "artist" if isinstance(profile, Artist) else "venue"
    return db.query(Request).filter(profile_request_filter(db, kind, profile.id))


def profile_facts(db: Session, kind: str, target_id: str):
    response = response_stats(db, kind, target_id)
    completed = (
        db.query(Booking)
        .join(Offer, Booking.offer_id == Offer.id)
        .join(Request, Offer.request_id == Request.id)
        .filter(
            profile_request_filter(db, kind, target_id),
            Booking.status == "Completed",
        )
        .count()
    )
    return {
        "deals": completed,
        "response": response["label"],
        "response_metrics": response,
        "note": "Завершённые сделки и время первого предложения рассчитаны по данным Букера.",
    }


def metrics(db: Session, org_id: str, days: int, profile=None):
    cutoff = now() - timedelta(days=days)
    req_query = (
        profile_requests(db, profile)
        if profile
        else db.query(Request).filter_by(supplier_org_id=org_id)
    )
    requests = req_query.filter(Request.created_at >= cutoff).all()
    request_ids = [r.id for r in requests]
    offers = db.query(Offer).filter(Offer.request_id.in_(request_ids)).all()
    bookings = db.query(Booking).filter(Booking.offer_id.in_([o.id for o in offers])).all()
    offer_requests = {o.request_id for o in offers}
    offer_by_id = {o.id: o for o in offers}
    held_bookings = {
        h.booking_id
        for h in db.query(BookingHold).filter(BookingHold.booking_id.in_([b.id for b in bookings]))
    }
    held_requests = {offer_by_id[b.offer_id].request_id for b in bookings if b.id in held_bookings}
    confirmed = [b for b in bookings if b.status in {"Confirmed", "InProgress", "Completed"}]
    completed = [b for b in bookings if b.status == "Completed"]
    confirmed_requests = {offer_by_id[b.offer_id].request_id for b in confirmed}
    completed_requests = {offer_by_id[b.offer_id].request_id for b in completed}
    honorarium = 0
    for booking in confirmed:
        version = db.get(OfferVersion, offer_by_id[booking.offer_id].active_version_id)
        if version:
            honorarium += version.honorarium_rub
    signals = db.query(DiscoverySignal).filter(
        DiscoverySignal.organization_id == org_id, DiscoverySignal.created_at >= cutoff
    )
    if profile:
        signals = signals.filter(DiscoverySignal.target_id == profile.id)
    signals = signals.all()
    impressions = sum(s.kind == "impression" for s in signals)
    views = len({s.visitor_key for s in signals if s.kind == "profile_view"})
    favorites = sum(s.kind == "favorite" for s in signals)
    first_offers = {}
    for offer in offers:
        first_offers[offer.request_id] = min(
            first_offers.get(offer.request_id, aware(offer.created_at)), aware(offer.created_at)
        )
    responses = [
        max(0, int((first_offers[r.id] - aware(r.created_at)).total_seconds()))
        for r in requests
        if r.id in first_offers
    ]
    values = {
        "impressions": impressions,
        "profile_views": views,
        "favorites": favorites,
        "requests": len(requests),
        "offers": len(offer_requests),
        "holds": len(held_requests),
        "confirmed": len(confirmed_requests),
        "completed": len(completed_requests),
    }
    losses = Counter()
    lost_requests = []
    for req in requests:
        if req.status != "Cancelled":
            continue
        observed = (
            db.query(AuditLog)
            .filter_by(action="request.loss_reason", entity_id=req.id)
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        reason = json.loads(observed.payload).get("reason", "unknown") if observed else "unknown"
        if reason not in LOSS_LABELS:
            reason = "unknown"
        losses[reason] += 1
        lost_requests.append({"request_id": req.id, "reason": reason, "label": LOSS_LABELS[reason]})
    return {
        "funnel": values,
        "confirmed_honorarium_rub": honorarium,
        "response": {
            "median_seconds": int(median(responses)) if responses else None,
            "sample_size": len(responses),
        },
        "conversions": {
            "request_to_offer": len(offer_requests) / len(requests) if requests else None,
            "request_to_confirmed": len(confirmed_requests) / len(requests) if requests else None,
            "profile_to_request": len(requests) / views if views else None,
            "impression_to_profile": views / impressions if impressions else None,
        },
        "losses": [{"reason": k, "label": LOSS_LABELS[k], "count": losses[k]} for k in LOSS_LABELS],
        "lost_requests": lost_requests,
    }


def growth_summary(db: Session, org_id: str, days: int, target_id: str | None = None):
    if days not in {7, 30, 90, 365}:
        raise HTTPException(422, "Выберите период 7, 30, 90 или 365 дней")
    org = db.get(Organization, org_id)
    if org.kind not in {"artist", "venue"}:
        raise HTTPException(422, "Раздел доступен исполнителям и площадкам")
    entitlement = get_entitlements(db, org_id)
    features = entitlement["features"]
    if days > features.get("analytics.days", 0):
        raise HTTPException(403, "Этот период доступен на расширенном тарифе")
    profiles = (
        db.query(Artist if org.kind == "artist" else Venue).filter_by(organization_id=org_id).all()
    )
    chosen = next((p for p in profiles if p.id == target_id), None) if target_id else None
    if target_id and not chosen:
        raise HTTPException(403, "Нет доступа к профилю")
    result = metrics(db, org_id, days, chosen)
    if not features.get("analytics.advanced"):
        result.pop("losses")
        result.pop("lost_requests")
    selected = [chosen] if chosen else profiles
    resource_ids = (
        [p.id for p in selected]
        if org.kind == "artist"
        else [
            h.id
            for h in db.query(VenueHall).filter(VenueHall.venue_id.in_([p.id for p in selected]))
        ]
    )
    slots = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.resource_id.in_(resource_ids),
            AvailabilitySlot.ends_at >= now(),
            AvailabilitySlot.starts_at < now() + timedelta(days=30),
        )
        .all()
    )
    usable = [
        slot
        for resource_id in resource_ids
        for slot in open_slots_unmasked([s for s in slots if s.resource_id == resource_id])
    ]
    dates = sorted({aware(s.starts_at).astimezone(MSK).date().isoformat() for s in usable})
    hints = []
    if org.kind == "artist" and any(not p.media_url for p in selected):
        hints.append("Добавьте основное видео в профили без медиа.")
    if not dates:
        hints.append("На ближайшие 30 дней нет открытых дат. Обновите календарь.")
    result.update(
        days=days,
        generated_at=now(),
        profiles=[{"id": p.id, "name": p.name} for p in profiles],
        selected_profile_id=target_id,
        available_periods=[d for d in (7, 30, 90, 365) if d <= features.get("analytics.days", 0)],
        open_dates=dates,
        suggestions=hints,
        can_export=bool(features.get("export.analytics")),
        methodology="Показы: один сигнал на профиль, сессию и день. Просмотры: уникальные сессии за период. Заявки созданы в выбранный период; последующие стадии отражают их текущее состояние. Между просмотрами и заявками показано отношение объёмов, а не когортная конверсия. Гонорары — сумма подтверждённых условий, не выплаченный доход.",
    )
    result["benchmark"] = (
        benchmark(db, org, selected, days)
        if features.get("analytics.benchmark")
        else {"status": "upgrade", "message": "Сравнение с похожими профилями доступно в Premium."}
    )
    return result


def benchmark(db: Session, org: Organization, selected: list, days: int):
    if len(selected) != 1:
        return {"status": "choose_profile", "message": "Выберите один профиль для сравнения."}
    profile = selected[0]
    model = Artist if org.kind == "artist" else Venue
    query = db.query(model).filter(model.city == profile.city, model.organization_id != org.id)
    if org.kind == "artist":
        query = query.filter(Artist.category == profile.category)
    else:
        query = query.filter(Venue.moderation_status == "published", Venue.is_claimed.is_(True))
    peers = query.all()
    # Separate organizations prevent one team's profiles from exposing another supplier.
    if len(peers) < 10 or len({p.organization_id for p in peers}) < 10:
        return {
            "status": "insufficient",
            "message": "Пока недостаточно похожих профилей для обезличенного сравнения.",
        }
    volumes = [
        profile_requests(db, p).filter(Request.created_at >= now() - timedelta(days=days)).count()
        for p in peers
    ]
    return {
        "status": "available",
        "cohort": "Не менее 10 независимых профилей того же города и категории",
        "median_requests": median(volumes),
        "message": "Медиана заявок за период. Имена и показатели отдельных профилей не раскрываются.",
    }


def record_loss(db: Session, req: Request, reason: str, actor_id: str, side: str):
    if req.status != "Cancelled":
        raise HTTPException(409, "Укажите причину после закрытия заявки")
    allowed = (
        {"price", "customer_selected_another", "event_cancelled", "unknown"}
        if side == "customer"
        else {"supplier_declined", "unknown"}
    )
    if reason not in allowed:
        raise HTTPException(422, "Эту причину может указать только соответствующая сторона")
    previous = (
        db.query(AuditLog)
        .filter_by(action="request.loss_reason", entity_id=req.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if previous:
        payload = json.loads(previous.payload)
        if payload.get("reason") == reason and previous.actor_user_id == actor_id:
            return
        # An actor cannot overwrite another party's first explicit explanation.
        raise HTTPException(409, "Причина уже зафиксирована")
    audit(
        db,
        actor_user_id=actor_id,
        action="request.loss_reason",
        entity_type="request",
        entity_id=req.id,
        payload={"reason": reason, "side": side, "organization_id": req.supplier_org_id},
    )
