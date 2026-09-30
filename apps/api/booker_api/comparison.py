"""Side-by-side public facts, preserving the caller's order rather than ranking profiles."""
from booker_api.compatibility import assess_compatibility, hall_facts, resource_available
from booker_api.composition import ROLE_LABEL
from booker_api.event_planning import ORIENTATION_NOTE, tariff_range
from booker_api.growth.service import profile_facts
from booker_api.models import ArtistTariff, VenueHall, VenueTariff
from booker_api.presentation import presentation_data
from booker_api.routers.reviews import profile_reviews
from booker_api.security import aware, now


def comparison_columns(db, kind, profiles, *, start=None, end=None, guests=None, own_slots=None, reference_artist=None, reference_venue=None, reference_hall=None, event_city=None):
    known_window = bool(start and end and aware(end) > aware(start) and aware(end) > now())
    columns = []

    def availability(resource_type, resource_id, *, before=0, after=0, owner=True):
        if not known_window or not owner:
            return {"status": "unknown", "label": "Доступность нужно уточнить", "explanation": "Нужно будущее окно с началом и окончанием и календарь владельца."}
        available = resource_available(db, resource_type, resource_id, aware(start), aware(end), before=before, after=after, own_slot_ids=own_slots)
        return {"status": "open" if available else "unavailable", "label": "Окно есть в календаре" if available else "Нет доступного окна",
                "explanation": "Календарь покрывает всё указанное время с известными буферами." if available else "Нет полного свободного окна или есть занятость с учётом буферов."}

    def compatibility(artist, venue, hall):
        if not artist or not venue or not hall:
            return None
        result = assess_compatibility(db, artist=artist, venue=venue, hall=hall, starts_at=start, ends_at=end,
            guest_count=guests, own_slot_ids=own_slots, event_city=event_city)
        return {k: result[k] for k in ("status", "status_label", "checks", "to_resolve", "hall")}

    for profile in profiles:
        reviews = profile_reviews(db, kind, profile.id, profile.organization_id)
        column = {"id": profile.id, "name": profile.name, "city": profile.city or None, "verified": bool(profile.verified),
                  "profile_href": f"/{'artists' if kind == 'artist' else 'venues'}/{profile.id}",
                  "facts": profile_facts(db, kind, profile.id),
                  "reviews": {"count": reviews["count"], "average_rating": reviews["average_rating"], "note": "Средняя оценка показывается от пяти отзывов по завершённым сделкам этого профиля."}}
        if kind == "artist":
            data = presentation_data(db, profile)[1]
            technical = data.get("technical") or {}
            prices = tariff_range(db.query(ArtistTariff).filter_by(artist_id=profile.id).all())
            column.update(category=profile.category, category_label=ROLE_LABEL.get(profile.category, "Исполнитель"), capacity=None,
                prices=prices, format=data.get("format") or None, lineup=data.get("lineup") or None,
                program=data.get("program") or None, genres=data.get("genres") or [], duration_minutes=data.get("duration_minutes"),
                travel_cities=data.get("travel_cities") or [], technical=technical, rider_text=data.get("rider_text") or None,
                portfolio={"primary_video": bool(data.get("primary_video_url")), "gallery_count": len(data.get("gallery") or []), "links_count": len(data.get("links") or [])},
                availability=availability("artist", profile.id, before=technical.get("setup_minutes") or 0, after=technical.get("teardown_minutes") or 0),
                buffers_known=technical.get("setup_minutes") is not None and technical.get("teardown_minutes") is not None,
                compatibility=compatibility(profile, reference_venue, reference_hall), halls=[])
        else:
            owner = profile.is_claimed and profile.availability_mode == "owner"
            halls = []
            for hall in db.query(VenueHall).filter_by(venue_id=profile.id).order_by(VenueHall.name, VenueHall.id).all():
                facts = hall_facts(db, hall)[1] if owner else None
                halls.append({"id": hall.id, "name": hall.name, "capacity": hall.capacity,
                    "capacity_status": "unknown" if guests is None else "fits" if hall.capacity >= guests else "too_small",
                    "technical": facts, "availability": availability("hall", hall.id, owner=owner),
                    "compatibility": compatibility(reference_artist, profile, hall)})
            prices = tariff_range(db.query(VenueTariff).filter_by(venue_id=profile.id).all())
            open_halls = [h for h in halls if h["availability"]["status"] == "open" and h["capacity_status"] != "too_small"]
            state = "unknown" if not known_window or not owner or not halls else "open" if open_halls else "unavailable"
            column.update(category="venue", category_label="Площадка", capacity=max((h["capacity"] for h in halls), default=profile.capacity),
                district=profile.district or None, metro=profile.metro or None, prices=prices, halls=halls,
                availability={"status": state, "label": "Есть зал на это окно" if state == "open" else "Доступность нужно уточнить" if state == "unknown" else "Нет подходящего свободного зала",
                              "explanation": "Проверяйте вместимость и условия конкретного зала. Общий тариф площадки не является ценой нескольких залов."},
                owner_calendar=owner, compatibility=None)
        column["honorarium_hint"] = "Стоимость не указана" if prices["min_rub"] is None else f"От {prices['min_rub']} ₽ за опубликованный пакет"
        columns.append(column)
    return {"target_type": kind, "columns": columns, "fields": ["name", "city", "category_label", "verified", "capacity", "honorarium_hint"],
            "starts_at": start, "ends_at": end, "guest_count": guests, "note": ORIENTATION_NOTE,
            "methodology": "Кандидаты показаны в порядке выбора. Подписка, продвижение и заполненность профиля не меняют факты доверия. Открытое окно не является резервом; неизвестное не означает соответствие. Цены — опубликованные пакеты без сервисного сбора."}
