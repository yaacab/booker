"""Explainable public-brief matching; paid plans change tools, never order access."""

import json
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.calendar import MSK, calendar_day_bounds, open_slots_unmasked
from booker_api.commerce.entitlements import get_entitlements
from booker_api.config import settings
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    BriefResponse,
    OpportunityDelivery,
    OpportunityFilter,
    Organization,
    PublicBrief,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.notifications.service import notify
from booker_api.notifications.types import Channel, Notification
from booker_api.security import audit, aware, membership, now

EVENT_TYPE_LABELS = {
    "corporate": "Корпоратив",
    "wedding": "Свадьба",
    "birthday": "День рождения",
    "private": "Частное событие",
    "festival": "Фестиваль",
    "conference": "Конференция",
    "other": "Другое событие",
}


def object_json(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def profiles_for(db: Session, org: Organization):
    model = Artist if org.kind == "artist" else Venue
    query = db.query(model).filter_by(organization_id=org.id)
    if org.kind == "venue":
        query = query.filter(
            Venue.moderation_status == "published",
            Venue.availability_mode == "owner",
            Venue.is_claimed.is_(True),
        )
    return query.all()


def public_data(brief: PublicBrief):
    return {
        "id": brief.id,
        "title": brief.title,
        "city": brief.city,
        "event_type": brief.event_type or "",
        "event_type_label": EVENT_TYPE_LABELS.get(brief.event_type, "Формат уточняется"),
        "date_from": aware(brief.date_from),
        "date_to": aware(brief.date_to),
        "role_needed": brief.role_needed,
        "guest_count_band": brief.guest_count_band,
        "public_notes": brief.public_notes,
        "budget_range": {"min_rub": brief.budget_min_rub, "max_rub": brief.budget_max_rub}
        if brief.share_budget
        else None,
        "public_requirements": object_json(brief.public_requirements_json),
        "status": brief.status,
    }


def match_profile(db: Session, profile, brief: PublicBrief):
    kind = "artist" if isinstance(profile, Artist) else "venue"
    if kind == "venue" and (
        profile.moderation_status != "published"
        or not profile.is_claimed
        or profile.availability_mode != "owner"
    ):
        return None
    category = profile.category if kind == "artist" else "venue"
    if brief.role_needed != category:
        return None
    rider = object_json(profile.rider_json) if kind == "artist" else {}
    same_city = profile.city.casefold().strip() == brief.city.casefold().strip()
    travel_cities = rider.get("travel_cities")
    valid_cities = isinstance(travel_cities, list) and all(
        isinstance(c, str) for c in travel_cities
    )
    travel = rider.get("travel_ok") is True and (
        not travel_cities
        or (
            valid_cities
            and brief.city.casefold().strip() in {c.casefold().strip() for c in travel_cities}
        )
    )
    if not same_city and not travel:
        return None
    start, end = aware(brief.date_from), aware(brief.date_to)
    if start == end:
        start, end = calendar_day_bounds(start)
    if end <= now():
        return None
    halls = db.query(VenueHall).filter_by(venue_id=profile.id).all() if kind == "venue" else []
    capacity_state = "unknown"
    if halls:
        band_max = {"1-50": 50, "51-100": 100, "101-200": 200}.get(brief.guest_count_band)
        if band_max:
            halls = [h for h in halls if h.capacity >= band_max]
            if not halls:
                return None
            capacity_state = "match"
        elif brief.guest_count_band == "200+":
            halls = [h for h in halls if h.capacity > 200]
            if not halls:
                return None
    targets = [profile.id] if kind == "artist" else [h.id for h in halls]
    open_dates = []
    for resource_id in targets:
        slots = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_id == resource_id,
                AvailabilitySlot.resource_type == ("artist" if kind == "artist" else "hall"),
                AvailabilitySlot.ends_at > max(start, now()),
                AvailabilitySlot.starts_at < end,
            )
            .all()
        )
        open_dates.extend(open_slots_unmasked(slots, day_start=start, day_end=end))
    if not open_dates:
        return None
    tariffs = (
        db.query(ArtistTariff).filter_by(artist_id=profile.id).all()
        if kind == "artist"
        else db.query(VenueTariff).filter_by(venue_id=profile.id).all()
    )
    minimum = min((t.honorarium_rub for t in tariffs), default=None)
    budget_state = "unknown"
    if brief.share_budget and brief.budget_max_rub is not None and minimum is not None:
        if minimum > brief.budget_max_rub:
            return None
        budget_state = "match"
    requirements = object_json(brief.public_requirements_json)
    equipment = requirements.get("equipment", [])
    declared = rider.get("equipment")
    technical_state = "unknown"
    if equipment and isinstance(declared, list):
        if not all(item in declared for item in equipment):
            return None
        technical_state = "match"
    reasons = [
        {"code": "category", "state": "match", "weight": 25, "label": "Роль совпадает с профилем"},
        {
            "code": "date",
            "state": "match",
            "weight": 30,
            "label": "Есть свободный слот в указанном диапазоне; длительность нужно согласовать",
        },
        {
            "code": "geography",
            "state": "match",
            "weight": 20,
            "label": "Тот же город" if same_city else "Выезд разрешён в профиле",
        },
        {
            "code": "budget",
            "state": budget_state,
            "weight": 15,
            "label": "Опубликованный тариф укладывается в диапазон"
            if budget_state == "match"
            else "Бюджет или тариф не опубликован",
        },
        {
            "code": "equipment",
            "state": technical_state,
            "weight": 10,
            "label": "Заявленное оборудование подходит"
            if technical_state == "match"
            else "Технические требования нужно уточнить",
        },
    ]
    if kind == "venue":
        reasons.append(
            {
                "code": "capacity",
                "state": capacity_state,
                "weight": 0,
                "label": "Вместимость подходит диапазону гостей"
                if capacity_state == "match"
                else "Точное число гостей нужно уточнить",
            }
        )
    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "score": sum(r["weight"] for r in reasons if r["state"] == "match"),
        "reasons": reasons,
        "orientation_honorarium_rub": minimum,
        "available_slot_id": open_dates[0].id,
        "methodology": "Сумма весов подтверждённых совпадений, максимум 100. Неизвестные данные не считаются совпадением. Это не вероятность сделки и не quote.",
    }


def filter_brief(brief: PublicBrief, query: dict):
    if query.get("city") and query["city"].casefold().strip() != brief.city.casefold().strip():
        return False
    if (
        query.get("date_from")
        and aware(brief.date_to).astimezone(MSK).date().isoformat() < query["date_from"]
    ):
        return False
    if (
        query.get("date_to")
        and aware(brief.date_from).astimezone(MSK).date().isoformat() > query["date_to"]
    ):
        return False
    return not (
        query.get("budget_min_rub") is not None
        and (
            not brief.share_budget
            or brief.budget_max_rub is None
            or brief.budget_max_rub < query["budget_min_rub"]
        )
    )


def match_brief(db: Session, profiles: list, brief: PublicBrief, query: dict):
    if (
        brief.status != "open"
        or aware(brief.date_to) < now() - timedelta(days=1)
        or not filter_brief(brief, query)
    ):
        return None
    matches = [
        match_profile(db, p, brief)
        for p in profiles
        if not query.get("target_id") or p.id == query["target_id"]
    ]
    matches = [m for m in matches if m and m["score"] >= query.get("minimum_score", 0)]
    return max(matches, key=lambda m: (m["score"], m["profile_id"])) if matches else None


def feed(db: Session, org: Organization, query: dict, limit=50):
    profiles = profiles_for(db, org)
    # Future open briefs only. All supplier tiers use the same matching policy.
    briefs = (
        db.query(PublicBrief)
        .filter(
            PublicBrief.status == "open",
            PublicBrief.date_to >= now() - timedelta(days=1),
            PublicBrief.organization_id != org.id,
        )
        .order_by(PublicBrief.date_from, PublicBrief.id)
        .all()
    )
    responses = {
        r.brief_id: r.id for r in db.query(BriefResponse).filter_by(supplier_org_id=org.id)
    }
    items = []
    for brief in briefs:
        match = match_brief(db, profiles, brief, query)
        if match:
            items.append(
                {**public_data(brief), "match": match, "response_id": responses.get(brief.id)}
            )
    items.sort(key=lambda item: (-item["match"]["score"], item["date_from"], item["id"]))
    return {
        "items": items[(query.get("page", 1) - 1) * limit : query.get("page", 1) * limit],
        "page": query.get("page", 1),
        "has_more": len(items) > query.get("page", 1) * limit,
        "total": len(items),
        "profiles": [{"id": p.id, "name": p.name} for p in profiles],
        "features": get_entitlements(db, org.id)["features"],
    }


def on_brief_published(db: Session, brief: PublicBrief):
    if not settings.opportunities:
        return
    filters = db.query(OpportunityFilter).filter_by(active=True, instant_alerts=True).all()
    for saved in filters:
        if not saved.consent_at or not membership(db, saved.user_id, saved.organization_id):
            continue
        if not get_entitlements(db, saved.organization_id)["features"].get(
            "opportunities.instant_alerts"
        ):
            continue
        org = db.get(Organization, saved.organization_id)
        if org.id == brief.organization_id or not match_brief(
            db, profiles_for(db, org), brief, json.loads(saved.query_json)
        ):
            continue
        try:
            with db.begin_nested():
                db.add(
                    OpportunityDelivery(
                        brief_id=brief.id, user_id=saved.user_id, filter_id=saved.id
                    )
                )
                db.flush()
                notify(
                    db,
                    actor_user_id=None,
                    notifications=[
                        Notification(
                            channel=Channel.IN_APP,
                            template="opportunity.matched",
                            recipient_user_id=saved.user_id,
                            subject="Новый подходящий заказ",
                            body=f"{brief.title} · {brief.city}",
                            entity_type="public_brief",
                            entity_id=brief.id,
                            metadata={
                                "organization_id": org.id,
                                "href": f"/cabinet/{'performer' if org.kind == 'artist' else 'venue'}/opportunities",
                            },
                        )
                    ],
                )
                audit(
                    db,
                    actor_user_id=None,
                    action="opportunity.alerted",
                    entity_type="public_brief",
                    entity_id=brief.id,
                    payload={"organization_id": org.id, "filter_id": saved.id},
                )
        except IntegrityError:
            pass
