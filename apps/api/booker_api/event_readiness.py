"""Read-only preparation checklist. A deal room is not a confirmed booking."""
import json
from collections import defaultdict

from booker_api.compatibility import assess_compatibility, event_slot_ids, resource_available
from booker_api.composition import ROLE_LABEL
from booker_api.event_budget import RESERVED, customer_amount, event_budget
from booker_api.models import (
    Artist,
    AvailabilitySlot,
    Booking,
    BookingHold,
    Contract,
    EventPlan,
    EventTeamRequirement,
    OfferVersion,
    Payment,
    Venue,
    VenueHall,
)
from booker_api.offer_validity import expired as quote_expired
from booker_api.presentation import presentation_data
from booker_api.security import aware, now

STAGES = [
    ("selected", "Участники выбраны"), ("offers", "Предложения получены"),
    ("acknowledged", "Условия подтверждены обеими сторонами"),
    ("reserved", "Даты закреплены"), ("contracts", "Договоры подписаны"),
    ("payments", "Оплата подтверждена"), ("confirmed", "Сделки подтверждены"),
]


def event_readiness(db, event):
    budget = event_budget(db, event)
    requirements = db.query(EventTeamRequirement).filter_by(event_id=event.id).order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id).all()
    plan = db.get(EventPlan, event.id)
    choices = {(s["requirement_id"], s["position"]): s for s in json.loads(plan.selections_json)} if plan else {}
    included = [line for line in budget["lines"] if line["included"]]
    by_unit = {(line["requirement_id"], line["position"]): line for line in included if line["position"] is not None}
    targets = []
    for role in requirements:
        if not role.required:
            continue
        for position in range(role.qty):
            key = (role.id, position)
            targets.append({"requirement_id": role.id, "position": position, "label": role.role_label or ROLE_LABEL.get(role.category_code, "Участник"),
                            "category": role.category_code, "line": by_unit.get(key), "choice": choices.get(key), "required": True})
    assigned = {t["line"]["booking_id"] for t in targets if t["line"]}
    for target in targets:
        if not target["line"]:
            expired = [line for line in budget["lines"] if line["requirement_id"] == target["requirement_id"] and line["booking_status"] in RESERVED and line["group"] == "excluded" and line["booking_id"] not in assigned]
            if len(expired) == 1 and (not target["choice"] or target["choice"]["resource_id"] == expired[0]["resource_id"]):
                target["line"] = expired[0]
                assigned.add(expired[0]["booking_id"])
    required_total = len(targets)
    required_keys = {(t["requirement_id"], t["position"]) for t in targets}
    for line in included:
        if (line["requirement_id"], line["position"]) not in required_keys and (line["group"] == "confirmed" or line["reserved"]):
            targets.append({"requirement_id": line["requirement_id"], "position": line["position"], "label": line["role_label"], "category": None, "line": line, "choice": None, "required": False})
    # Captured money on a closed/unconfirmed alternative still needs operator attention.
    represented = {t["line"]["booking_id"] for t in targets if t["line"]}
    for line in budget["lines"]:
        if line["booking_id"] not in represented and line["group"] == "excluded" and db.query(Payment).filter_by(booking_id=line["booking_id"], status="succeeded").first():
            targets.append({"requirement_id": line["requirement_id"], "position": None, "label": line["role_label"], "category": None, "line": line, "choice": None, "required": False})
    ids = [t["line"]["booking_id"] for t in targets if t["line"]]
    bookings = {b.id: b for b in db.query(Booking).filter(Booking.id.in_(ids)).all()} if ids else {}
    contracts, payments, holds = defaultdict(list), defaultdict(list), defaultdict(list)
    for model, dest in [(Contract, contracts), (Payment, payments), (BookingHold, holds)]:
        for row in db.query(model).filter(model.booking_id.in_(ids)).all() if ids else []:
            dest[row.booking_id].append(row)
    own_slots = event_slot_ids(db, event.id)
    window = bool(event.ends_at and aware(event.ends_at) > aware(event.event_date) and aware(event.ends_at) > now())
    actions, participants, stage_values, test_payments = [], [], defaultdict(list), 0

    def action(code, label, description, href, priority):
        value = {"code": code, "label": label, "description": description, "href": href, "priority": priority}
        if value not in actions:
            actions.append(value)

    if not window:
        action("event_window", "Уточнить окно события", "Нужны начало и окончание будущего события.", f"/events/{event.id}#matching", 10)
    if not required_total:
        action("requirements", "Указать обязательные роли", "Готовность рассчитывается по обязательному составу.", f"/events/{event.id}#event-roles", 10)
    for target in targets:
        line, choice = target["line"], target["choice"]
        selection = line or choice
        booking = bookings.get(line["booking_id"]) if line else None
        version = db.get(OfferVersion, line["quote_id"]) if line and line["quote_id"] else None
        slot = db.get(AvailabilitySlot, booking.slot_id) if booking else None
        artist = db.get(Artist, selection["resource_id"]) if selection and selection["resource_type"] == "artist" else None
        hall = db.get(VenueHall, selection.get("hall_id")) if selection and selection.get("hall_id") else None
        venue = db.get(Venue, hall.venue_id) if hall else None
        selected = bool(artist or hall)
        if target["category"]:
            selected = selected and (artist.category == target["category"] if artist else target["category"] == "venue")
        name = artist.name if artist else f"{venue.name} · {hall.name}" if venue and hall else target["label"]
        live_hold = bool(booking and slot and slot.status == "held" and any(h.status == "active" and h.slot_id == booking.slot_id and aware(h.expires_at) > now() for h in holds[booking.id]))
        confirmed = bool(booking and booking.status in {"Confirmed", "InProgress", "Completed"})
        reserved = bool(booking and slot and (confirmed and slot.status == "confirmed" or booking.status in RESERVED and live_hold))
        signed = bool(booking and any(c.customer_signed and c.supplier_signed for c in contracts[booking.id]))
        amount = customer_amount(version)
        captures = [p for p in payments[booking.id] if p.status == "succeeded"] if booking else []
        paid = amount is not None and amount > 0 and sum(p.amount_rub for p in captures) >= amount
        is_test = paid and any(p.provider == "stub" for p in captures)
        test_payments += int(is_test)
        expired = bool(booking and booking.status in RESERVED and not live_hold)
        offer_expired = bool(booking and booking.status == "Negotiation" and quote_expired(version))
        flags = {"selected": selected, "offers": version is not None and not expired and not offer_expired, "acknowledged": bool(version and version.customer_ack and version.supplier_ack and not expired and not offer_expired),
                 "reserved": reserved, "contracts": signed and not expired, "payments": paid, "confirmed": confirmed}
        for key, value in flags.items():
            stage_values[key].append(value)
        href = line["href"] if line else f"/events/{event.id}#matching"
        technical = presentation_data(db, artist)[1].get("technical") or {} if artist else {}
        calendar_ok = None
        if selected and window:
            calendar_ok = resource_available(db, "artist" if artist else "hall", artist.id if artist else hall.id,
                aware(event.event_date), aware(event.ends_at), own_slot_ids=own_slots,
                before=technical.get("setup_minutes") or 0, after=technical.get("teardown_minutes") or 0)
            if booking:
                expected_kind, expected_id = ("artist", artist.id) if artist else ("hall", hall.id)
                calendar_ok = calendar_ok and bool(slot and slot.resource_type == expected_kind and slot.resource_id == expected_id
                    and aware(slot.starts_at) <= aware(event.event_date) and aware(slot.ends_at) >= aware(event.ends_at))
            if hall:
                calendar_ok = calendar_ok and bool(venue.is_claimed and venue.availability_mode == "owner" and hall.capacity >= event.guest_count and venue.city.strip().casefold() == event.city.strip().casefold())
        participant = {"name": name, "role_label": target["label"], "requirement_id": target["requirement_id"], "position": target["position"],
                       "required": target["required"], "booking_id": booking.id if booking else None, "href": href, "checks": flags,
                       "calendar_status": "compatible" if calendar_ok else "incompatible" if calendar_ok is False else "unknown", "test_payment": is_test}
        participants.append(participant)
        target.update(artist=artist, hall=hall, venue=venue, participant=participant)
        inconsistent = booking and booking.status in {"Confirmed", "InProgress"} and not all([version is not None, flags["acknowledged"], reserved, signed, paid])
        if booking and (booking.status == "Dispute" or captures and not confirmed and not live_hold or inconsistent):
            reason = "открыт спор." if booking.status == "Dispute" else "поступила оплата без закреплённой даты." if captures and not confirmed and not live_hold else "подтверждённый статус не согласуется с резервом, документами или оплатой."
            action("operator", "Проверить сделку с поддержкой", f"{name}: {reason}", href, 0)
        elif expired:
            action("hold_expired", "Перепроверить выбор после истечения резерва", f"{name}: дата больше не удерживается; прежние подписи не подтверждают новый резерв.", href, 5)
        elif calendar_ok is False:
            action("calendar", "Перепроверить дату и условия", f"{name}: календарь или параметры площадки не покрывают событие.", href, 5)
        elif not selected:
            action("select", "Выбрать участника", f"{target['label']}: выберите участника или одно из полученных предложений.", f"/events/{event.id}#matching", 30)
        elif not version:
            action("request", "Запросить предложение", f"{name}: нужен ответ с условиями сделки.", f"/events/{event.id}#matching", 40)
        elif offer_expired:
            action("offer_expired", "Согласовать новые условия", f"{name}: срок предложения истёк.", href, 20)
        elif not flags["acknowledged"]:
            action("acknowledge", "Проверить условия предложения", f"{name}: " + ("нужно ваше подтверждение условий." if not version.customer_ack else "ждём подтверждения исполнителя."), href, 25 if not version.customer_ack else 55)
        elif not reserved:
            action("reserve", "Закрепить дату", f"{name}: действующий резерв или подтверждённая дата отсутствует.", href, 20)
        elif not signed:
            action("contract", "Перейти к договору", f"{name}: нужны подписи обеих сторон.", href, 25)
        elif not paid:
            action("payment", "Перейти к оплате", f"{name}: подтверждение оплаты ещё не получено. Доступность оплаты указана в сделке.", href, 25)
        elif not confirmed:
            action("confirmation", "Проверить подтверждение сделки", f"{name}: оплата не заменяет подтверждённое бронирование.", href, 5)
        if live_hold:
            deadline = min(aware(h.expires_at) for h in holds[booking.id] if h.status == "active" and aware(h.expires_at) > now())
            if (deadline - now()).total_seconds() <= 3600:
                action("hold_expiring", "Завершить сделку до истечения резерва", f"{name}: резерв истекает в ближайший час.", href, 15)

    # Check real selected artist/hall pairs; missing facts remain an explicit blocker.
    compatibility = []
    halls = [t for t in targets if t.get("hall") and t.get("venue")]
    for target in targets:
        artist = target.get("artist")
        if not artist:
            continue
        pairs = [assess_compatibility(db, artist=artist, venue=h["venue"], hall=h["hall"], starts_at=event.event_date,
                 ends_at=event.ends_at, guest_count=event.guest_count, event_city=event.city, own_slot_ids=own_slots) for h in halls]
        pair = min(pairs, key=lambda p: (p["status"] == "incompatible", len(p["to_resolve"]), p["hall"]["id"])) if pairs else None
        compatibility.append({"artist_id": artist.id, "artist_name": artist.name, "status": pair["status"] if pair else "unknown",
                              "hall_name": pair["hall"]["name"] if pair else None,
                              "to_resolve": pair["to_resolve"] if pair else [{"label": "Площадка", "explanation": "Зал не выбран в составе: техника на месте проведения не проверена."}]})
        if not pair or pair["status"] != "compatible":
            action("compatibility", "Согласовать технические условия", f"{artist.name}: " + ("есть несоответствие." if pair and pair["status"] == "incompatible" else "остались непроверенные условия."), f"/compatibility?event={event.id}&artist={artist.id}" + (f"&venue={pair['venue']['id']}&hall={pair['hall']['id']}" if pair else ""), 35)
    checklist = []

    def check(code, label, done, total, unknown=False, note=""):
        checklist.append({"code": code, "label": label, "done": done, "total": total,
                          "status": "not_applicable" if total == 0 else "done" if done == total else "unknown" if unknown else "pending", "note": note})

    check("window", "Окно события указано", int(window), 1)
    check("requirements", "Обязательный состав указан", int(required_total > 0), 1)
    for code, label in STAGES:
        check(code, label, sum(stage_values[code]), len(targets))
    check("calendar", "Календари и параметры площадок проверены", sum(p["calendar_status"] == "compatible" for p in participants), len(targets), any(p["calendar_status"] == "unknown" for p in participants))
    check("compatibility", "Райдеры сопоставлены с залами", sum(p["status"] == "compatible" for p in compatibility), len(compatibility), any(p["status"] == "unknown" for p in compatibility), "Отсутствующая техника не считается согласованной. Для своей площадки вне каталога нужна отдельная проверка условий; сводка не подтверждает её автоматически.")
    venue_targets = [t for t in targets if t["category"] == "venue"]
    check("venue", "Площадка выбрана", sum(bool(t.get("hall")) for t in venue_targets), len(venue_targets))
    total = sum(c["total"] for c in checklist)
    done = sum(c["done"] for c in checklist)
    score = done * 100 // total if total and required_total else 0
    ready = required_total > 0 and done == total and not any(a["code"] == "operator" for a in actions)
    state = "ready" if ready else "planning"
    if event.status in {"Cancelled", "Completed", "InProgress"}:
        state = {"Cancelled": "cancelled", "Completed": "completed", "InProgress": "in_progress"}[event.status]
        if event.status in {"Cancelled", "Completed"}:
            actions = [a for a in actions if a["code"] == "operator"]
        ready = False
    actions.sort(key=lambda a: (a["priority"], a["href"], a["code"]))
    next_action = actions[0] if actions else {"code": state, "label": "Открыть событие", "description": "Перейдите к сопровождению события." if state in {"ready", "in_progress"} else "Посмотрите сохранённые сведения события.", "href": f"/events/{event.id}#event-day"}
    return {"event_id": event.id, "state": state, "event_ready": ready, "score": None if state in {"cancelled", "completed"} else score,
            "required_total": required_total, "required_confirmed": sum(p["required"] and p["checks"]["confirmed"] for p in participants),
            "checklist": checklist, "participants": participants, "compatibility": compatibility,
            "blockers": [{k: v for k, v in a.items() if k != "priority"} for a in actions],
            "next_best_action": {k: v for k, v in next_action.items() if k != "priority"}, "test_payments": test_payments,
            "methodology": "Доля выполненных проверок обязательного состава и уже закреплённых дополнительных сделок. Это не вероятность успеха и не гарантия проведения. Неизвестное не даёт баллов. Проверка не изменяет сделки и не запрещает их дальнейшее оформление."}
