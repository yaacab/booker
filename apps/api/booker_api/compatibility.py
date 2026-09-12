"""Deterministic compatibility of declared facts. Unknown is never a positive match."""
import json
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from booker_api.calendar import ranges_overlap
from booker_api.models import (
    Artist,
    AvailabilitySlot,
    Booking,
    BookingHold,
    HallTechnicalProfile,
    Venue,
    VenueHall,
)
from booker_api.presentation import ShortText, presentation_data
from booker_api.security import aware, now

LABELS = {"compatible": "Подходит", "attention": "Нужно согласовать", "incompatible": "Есть несоответствие", "unknown": "Недостаточно данных"}


class HallFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity: int = Field(strict=True, ge=1, le=100000)
    stage_area_m2: float | None = Field(default=None, ge=0, le=10000)
    power_kw: float | None = Field(default=None, ge=0, le=10000)
    basic_sound: bool | None = None
    microphones: int | None = Field(default=None, strict=True, ge=0, le=100)
    equipment: list[ShortText] | None = Field(default=None, max_length=50)
    restrictions: str | None = Field(default=None, max_length=4000)


def hall_facts(db: Session, hall: VenueHall) -> tuple[int, dict]:
    row = db.get(HallTechnicalProfile, hall.id)
    if row:
        return row.version, json.loads(row.data_json)
    return 0, HallFacts(capacity=hall.capacity).model_dump()


def resource_available(db: Session, kind: str, target_id: str, start: datetime, end: datetime,
                       *, before=0, after=0, own_slot_ids: set[str] | None = None,
                       slots: list[AvailabilitySlot] | None = None) -> bool:
    """Cover the complete interval and account for both declared and calendar buffers."""
    own = own_slot_ids or set()
    if slots is None:
        slots = db.query(AvailabilitySlot).filter_by(resource_type=kind, resource_id=target_id).all()
    for slot in slots:
        if slot.status != "open" and not (slot.id in own and slot.status in {"held", "confirmed"}):
            continue
        if aware(slot.starts_at) > start or aware(slot.ends_at) < end:
            continue
        if (aware(slot.starts_at) - timedelta(minutes=slot.buffer_before_min or 0) > start - timedelta(minutes=before)
                or aware(slot.ends_at) + timedelta(minutes=slot.buffer_after_min or 0) < end + timedelta(minutes=after)):
            continue
        incoming_start = start - timedelta(minutes=max(before, slot.buffer_before_min or 0))
        incoming_end = end + timedelta(minutes=max(after, slot.buffer_after_min or 0))
        blocked = [s for s in slots if s.id != slot.id and s.status in {"busy", "held", "confirmed"}
                   and ranges_overlap(incoming_start, incoming_end,
                       aware(s.starts_at) - timedelta(minutes=max(0, s.buffer_before_min or 0)),
                       aware(s.ends_at) + timedelta(minutes=max(0, s.buffer_after_min or 0)))]
        if not any(s.status == "busy" or s.id not in own for s in blocked):
            return True
    return False


def assess_compatibility(db: Session, *, artist: Artist, venue: Venue, hall: VenueHall | None,
                         starts_at: datetime | None, ends_at: datetime | None, guest_count: int | None,
                         own_slot_ids: set[str] | None = None, event_city: str | None = None,
                         artist_data: dict | None = None, hall_data: tuple | None = None,
                         slot_cache: dict | None = None) -> dict:
    presentation = artist_data if artist_data is not None else presentation_data(db, artist)[1]
    artist_facts = presentation.get("technical") or {}
    hall_version, facts = hall_data if hall_data is not None else hall_facts(db, hall) if hall else (None, {})
    owner_facts = venue.is_claimed and venue.availability_mode == "owner"
    if not owner_facts:
        facts = {}
    checks = []

    def available(kind, target_id, start, end, **kwargs):
        return resource_available(db, kind, target_id, start, end, own_slot_ids=own_slot_ids,
                                  slots=slot_cache.get((kind, target_id), []) if slot_cache is not None else None, **kwargs)

    def check(code, label, state, explanation):
        checks.append({"code": code, "label": label, "status": state, "status_label": LABELS[state], "explanation": explanation})

    def minimum(code, label, needed, available, unit=""):
        if needed is None:
            check(code, label, "unknown", "Артист не указал требование")
        elif needed == 0:
            check(code, label, "compatible", "Не требуется по данным артиста")
        elif available is None:
            check(code, label, "unknown", f"Требуется {needed}{unit}; параметры зала не указаны")
        else:
            check(code, label, "compatible" if available >= needed else "incompatible", f"Требуется {needed}{unit}; в зале {available}{unit}")

    if event_city and venue.city.strip().casefold() != event_city.strip().casefold():
        check("geography", "География", "incompatible", f"Событие в городе {event_city}; площадка — {venue.city}")
    elif not artist.city or not venue.city:
        check("geography", "География", "unknown", "Города участников не указаны")
    elif artist.city.strip().casefold() == venue.city.strip().casefold():
        check("geography", "География", "compatible", f"Артист и площадка: {venue.city}")
    elif venue.city.strip().casefold() in {c.strip().casefold() for c in presentation.get("travel_cities", [])}:
        check("geography", "География", "compatible", f"В профиле артиста указан выезд: {venue.city}")
    else:
        check("geography", "География", "unknown", f"Согласуйте выезд артиста из города {artist.city} в город {venue.city}")
    capacity = facts.get("capacity")
    if guest_count is None or capacity is None:
        check("capacity", "Вместимость", "unknown", "Уточните число гостей и вместимость выбранного зала")
    else:
        check("capacity", "Вместимость", "compatible" if capacity >= guest_count else "incompatible", f"Гостей: {guest_count}; вместимость зала: {capacity}")
    start, end = (aware(starts_at) if starts_at else None), (aware(ends_at) if ends_at else None)
    interval_known = start is not None and end is not None and end > start and end > now()
    if not interval_known:
        check("date", "Дата и время", "unknown", "Укажите будущую дату, начало и окончание события")
    elif not hall or not owner_facts:
        check("date", "Дата и время", "unknown", "Нужен выбранный зал с календарём владельца")
    else:
        artist_open = available("artist", artist.id, start, end)
        hall_open = available("hall", hall.id, start, end)
        check("date", "Дата и время", "compatible" if artist_open and hall_open else "incompatible",
              "Оба календаря покрывают всё время события" if artist_open and hall_open else "Нет доступного окна на всё время события у артиста или зала")
    setup, teardown = artist_facts.get("setup_minutes"), artist_facts.get("teardown_minutes")
    if setup is None or teardown is None or not interval_known or not hall or not owner_facts:
        check("buffers", "Монтаж и демонтаж", "unknown", "Уточните время монтажа, демонтажа и окна в календарях")
    else:
        fits = available("artist", artist.id, start, end, before=setup, after=teardown) and available("hall", hall.id, start, end, before=setup, after=teardown)
        check("buffers", "Монтаж и демонтаж", "compatible" if fits else "incompatible", f"До события нужно {setup} мин.; после — {teardown} мин. " + ("Времени достаточно." if fits else "Свободного окна недостаточно."))
    minimum("stage", "Сцена", artist_facts.get("stage_area_m2"), facts.get("stage_area_m2"), " м²")
    minimum("power", "Электропитание", artist_facts.get("power_kw"), facts.get("power_kw"), " кВт")
    sound_needed, sound_available = artist_facts.get("basic_sound"), facts.get("basic_sound")
    if sound_needed is False:
        check("sound", "Базовый звук", "compatible", "Звук площадки не требуется по данным артиста")
    elif sound_needed is None or sound_available is None:
        check("sound", "Базовый звук", "unknown", "Нужно уточнить требования артиста и звуковое оборудование зала")
    else:
        check("sound", "Базовый звук", "compatible" if sound_available else "incompatible", "Звук предоставляется залом" if sound_available else "Артисту нужен звук площадки, в зале он не предоставляется")
    minimum("microphones", "Микрофоны", artist_facts.get("microphones"), facts.get("microphones"), " шт.")
    required, supplied, equipment = artist_facts.get("required_equipment"), artist_facts.get("supplied_equipment"), facts.get("equipment")
    missing = []
    if required is None:
        check("equipment", "Оборудование и DJ-пульт", "unknown", "Артист не указал обязательное оборудование")
    else:
        brought = {s.strip().casefold() for s in supplied or []}
        remaining = [item for item in required if item.strip().casefold() not in brought]
        if not remaining:
            check("equipment", "Оборудование и DJ-пульт", "compatible", "Дополнительное оборудование не требуется или его привозит артист")
        elif equipment is None:
            check("equipment", "Оборудование и DJ-пульт", "unknown", "Нужны: " + ", ".join(remaining) + ". Оснащение зала не указано")
        else:
            available = {s.strip().casefold() for s in equipment}
            missing = [item for item in remaining if item.strip().casefold() not in available]
            check("equipment", "Оборудование и DJ-пульт", "incompatible" if missing else "compatible", "Не хватает: " + ", ".join(missing) if missing else "Обязательное оборудование указано в оснащении зала")
    if facts.get("restrictions") is None:
        check("restrictions", "Ограничения площадки", "unknown", "Ограничения зала не указаны")
    elif facts["restrictions"]:
        check("restrictions", "Ограничения площадки", "attention", facts["restrictions"])
    else:
        check("restrictions", "Ограничения площадки", "compatible", "Владелец отметил отсутствие дополнительных ограничений")
    statuses = [c["status"] for c in checks]
    status = ("incompatible" if "incompatible" in statuses else "unknown" if all(s == "unknown" for s in statuses)
              else "attention" if any(s in {"unknown", "attention"} for s in statuses) else "compatible")
    return {"status": status, "status_label": LABELS[status], "score": None if all(s == "unknown" for s in statuses) else round(100 * statuses.count("compatible") / len(statuses)),
            "checks": checks, "to_resolve": [c for c in checks if c["status"] != "compatible"], "missing_required_items": missing,
            "artist": {"id": artist.id, "name": artist.name}, "venue": {"id": venue.id, "name": venue.name},
            "hall": {"id": hall.id, "name": hall.name, "version": hall_version} if hall else None,
            "starts_at": start, "ends_at": end, "guest_count": guest_count,
            "methodology": "Доля проверок с подтверждённым совпадением по введённым данным. Не вероятность успеха и не гарантия. Неизвестное не даёт баллов; названия оборудования сравниваются точно без учёта регистра.",
            "note": "Параметры указаны участниками. Согласуйте оставшиеся вопросы до подтверждения условий."}


def event_slot_ids(db: Session, event_id: str) -> set[str]:
    """Only authorized event services may use these slots as owned reservations."""
    result = set()
    for booking in db.query(Booking).filter_by(event_id=event_id).all():
        if booking.status in {"Confirmed", "InProgress"}:
            result.add(booking.slot_id)
        elif booking.status in {"DateHeld", "AwaitingContract", "AwaitingPayment"}:
            hold = db.query(BookingHold).filter_by(booking_id=booking.id, status="active").first()
            if hold and aware(hold.expires_at) > now():
                result.add(booking.slot_id)
    return result
