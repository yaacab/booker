"""Customer event budget: quote snapshots and tentative hints are separate ledgers."""
import json
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from booker_api.composition import ROLE_LABEL
from booker_api.event_planning import ORIENTATION_NOTE, tariff_range
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Booking,
    BookingHold,
    Event,
    EventPlan,
    EventTeamRequirement,
    Offer,
    OfferVersion,
    Request,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.security import aware, now
from booker_api.venue_catalog import is_publicly_listed

CONFIRMED = {"Confirmed", "InProgress", "Completed", "Dispute"}
RESERVED = {"DateHeld", "AwaitingContract", "AwaitingPayment"}
CLOSED_REQUESTS = {"Cancelled", "Declined", "Expired"}


def customer_amount(version):
    if not version or version.currency != "RUB":
        return None
    # Historic snapshots keep their own total; never reconstruct them with today's fees.
    return version.customer_total_rub if version.customer_total_rub is not None else version.total_rub


def event_budget(db: Session, event: Event) -> dict:
    requirements = db.query(EventTeamRequirement).filter_by(event_id=event.id).order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id).all()
    by_req = {r.id: r for r in requirements}
    units = {(r.id, i): {"requirement_id": r.id, "position": i, "label": r.role_label or ROLE_LABEL.get(r.category_code, "Участник"), "required": r.required}
             for r in requirements for i in range(r.qty)}
    plan = db.get(EventPlan, event.id)
    saved = json.loads(plan.selections_json) if plan else []
    selected = {(s["requirement_id"], s["position"]): s for s in saved if (s["requirement_id"], s["position"]) in units}
    rows = (db.query(Booking, Offer, Request, OfferVersion, AvailabilitySlot)
            .join(Offer, Booking.offer_id == Offer.id).join(Request, Offer.request_id == Request.id)
            .outerjoin(OfferVersion, Offer.active_version_id == OfferVersion.id)
            .outerjoin(AvailabilitySlot, Booking.slot_id == AvailabilitySlot.id)
            .filter(Booking.event_id == event.id).order_by(Booking.created_at, Booking.id).all())
    holds = defaultdict(list)
    for hold in db.query(BookingHold).filter(BookingHold.booking_id.in_([r[0].id for r in rows])).all() if rows else []:
        holds[hold.booking_id].append(hold)
    warnings, lines = [], []
    for booking, offer, req, version, slot in rows:
        live_hold = any(h.status == "active" and aware(h.expires_at) > now() for h in holds[booking.id])
        group = "confirmed" if booking.status in CONFIRMED else "active_offer" if req.status not in CLOSED_REQUESTS and (booking.status == "Negotiation" or booking.status in RESERVED and live_hold) else "excluded"
        label = (by_req[req.requirement_id].role_label or ROLE_LABEL.get(by_req[req.requirement_id].category_code, "Участник")) if req.requirement_id in by_req else "Без позиции состава"
        artist = db.get(Artist, req.resource_id) if req.resource_type == "artist" else None
        hall = db.get(VenueHall, slot.resource_id) if slot and slot.resource_type == "hall" else None
        venue = db.get(Venue, hall.venue_id if hall else req.resource_id) if req.resource_type in {"venue", "hall"} else None
        name = artist.name if artist else f"{venue.name} · {hall.name}" if venue and hall else venue.name if venue else "Участник сделки"
        line = {"booking_id": booking.id, "quote_id": version.id if version else None, "requirement_id": req.requirement_id,
                "role_label": label, "name": name, "resource_type": "artist" if artist else "venue",
                "resource_id": artist.id if artist else venue.id if venue else req.resource_id,
                "hall_id": hall.id if hall else None, "booking_status": booking.status, "group": group,
                "customer_total_rub": customer_amount(version), "included": False, "reason": "", "position": None,
                "href": f"/deals/{booking.id}", "reserved": booking.status in RESERVED and live_hold}
        if booking.status in RESERVED and not live_hold:
            line["reason"] = "Удержание истекло или отсутствует; предложение не включено в расчёт"
            warnings.append("Есть сделки без действующего удержания. Проверьте дату в комнате сделки.")
        elif group == "excluded":
            line["reason"] = "Закрытая сделка или заявка не входит в планируемый состав"
        if booking.status in {"Cancelled", "Dispute"}:
            warnings.append("Есть отмена или спор: удержания и возвраты по ним нужно смотреть отдельно в комнате сделки. Эта сводка не рассчитывает окончательный взаиморасчёт.")
        if group != "excluded" and line["customer_total_rub"] is None:
            warnings.append("У части сделок отсутствует рублёвый снимок цены; общая сумма неполная.")
        lines.append(line)

    occupied = set()

    def matches(line, choice):
        return (line["resource_type"] == choice["resource_type"] and line["resource_id"] == choice["resource_id"]
                and (choice["resource_type"] != "venue" or line["hall_id"] == choice.get("hall_id")))

    def assign(line):
        keys = [k for k in units if k[0] == line["requirement_id"] and k not in occupied]
        preferred = [k for k in keys if k in selected and matches(line, selected[k])]
        if preferred or keys:
            key = (preferred or keys)[0]
            occupied.add(key)
            line["position"] = key[1]
        line["included"] = True

    # All committed and held deals are liabilities, even duplicates or removed roles.
    for line in lines:
        if line["group"] == "confirmed" or line["reserved"]:
            assign(line)
            line["reason"] = "Подтверждённая сделка" if line["group"] == "confirmed" else "Действующее удержание"
            if line["position"] is None:
                warnings.append("Есть подтверждённые или удерживаемые сделки сверх состава либо без роли. Они включены в сумму полностью.")
    for key in sorted(units, key=lambda k: k not in selected):
        if key in occupied:
            continue
        candidates = [l for l in lines if l["group"] == "active_offer" and not l["included"] and l["requirement_id"] == key[0]]
        choice = selected.get(key)
        candidates = [l for l in candidates if matches(l, choice)] if choice else candidates
        # Explicit choices are assigned before the remaining unambiguous positions.
        open_units = [k for k in units if k[0] == key[0] and k not in occupied and k not in selected]
        unique_resources = {(l["resource_type"], l["resource_id"], l["hall_id"]) for l in candidates}
        if candidates and ((choice and len(candidates) == 1) or (not choice and len(candidates) <= len(open_units) and len(unique_resources) == len(candidates))):
            line = candidates[0]
            line["included"], line["position"] = True, key[1]
            line["reason"] = "Выбран в предварительном составе" if choice else "Нет конкурирующих предложений сверх нужного количества"
            occupied.add(key)
    for line in lines:
        if line["group"] == "active_offer" and not line["included"]:
            line["reason"] = "Альтернатива: выберите участника в предварительном составе" if line["requirement_id"] in by_req else "Нет позиции состава: предложение показано отдельно"

    # Hints cover only positions left without an included quote, never the same participant twice.
    hints = []
    used = {(l["resource_type"], l["resource_id"], l["hall_id"]) for l in lines if l["included"]}
    for key, choice in selected.items():
        if key in occupied:
            continue
        identity = (choice["resource_type"], choice["resource_id"], choice.get("hall_id"))
        prices, name = None, "Ранее выбранный участник"
        req = by_req[key[0]]
        if identity not in used and choice["resource_type"] == "artist":
            artist = db.get(Artist, choice["resource_id"])
            if artist and artist.category == req.category_code:
                name, prices = artist.name, tariff_range(db.query(ArtistTariff).filter_by(artist_id=artist.id).all())
        elif identity not in used and choice["resource_type"] == "venue":
            venue = db.get(Venue, choice["resource_id"])
            hall = db.get(VenueHall, choice.get("hall_id")) if choice.get("hall_id") else None
            if req.category_code == "venue" and venue and is_publicly_listed(db, venue) and hall and hall.venue_id == venue.id:
                name, prices = f"{venue.name} · {hall.name}", tariff_range(db.query(VenueTariff).filter_by(venue_id=venue.id).all())
        hints.append({**units[key], **choice, "name": name, "min_rub": prices["min_rub"] if prices else None, "max_rub": prices["max_rub"] if prices else None})
        used.add(identity)
    venue_counts = Counter(i["resource_id"] for i in hints if i["resource_type"] == "venue")
    # A general venue tariff cannot price multiple halls or augment an existing hall quote.
    quoted_venues = {l["resource_id"] for l in lines if l["included"] and l["resource_type"] == "venue"}
    for hint in hints:
        if hint["resource_type"] == "venue" and (venue_counts[hint["resource_id"]] > 1 or hint["resource_id"] in quoted_venues):
            hint["min_rub"] = hint["max_rub"] = None
    known_hints = [i for i in hints if i["min_rub"] is not None]
    confirmed = [l for l in lines if l["included"] and l["group"] == "confirmed"]
    offers = [l for l in lines if l["included"] and l["group"] == "active_offer"]
    confirmed_total = sum(l["customer_total_rub"] or 0 for l in confirmed)
    offers_total = sum(l["customer_total_rub"] or 0 for l in offers)
    uncovered = [u for k, u in units.items() if k not in occupied]
    unknown_quotes = any(l["customer_total_rub"] is None for l in [*confirmed, *offers])
    uncertain = unknown_quotes or any(u["required"] for u in uncovered)
    remaining = event.budget_rub - confirmed_total - offers_total if event.budget_rub is not None else None
    state = "no_budget" if remaining is None else "over_budget" if remaining < 0 else "partial" if uncertain or not units else "within_budget"
    return {"event_id": event.id, "declared_budget": event.budget_rub, "currency": "RUB",
            "confirmed_total": confirmed_total if all(l["customer_total_rub"] is not None for l in confirmed) else None,
            "active_offers_total": offers_total if all(l["customer_total_rub"] is not None for l in offers) else None,
            "estimated_remaining": None if unknown_quotes else remaining, "remaining_after_confirmed": event.budget_rub - confirmed_total if event.budget_rub is not None and all(l["customer_total_rub"] is not None for l in confirmed) else None,
            "state": state, "uncovered_requirements": uncovered, "lines": lines, "warnings": list(dict.fromkeys(warnings)),
            "orientation": {"min_rub": sum(i["min_rub"] for i in known_hints) if known_hints else None,
                            "max_rub": sum(i["max_rub"] for i in known_hints) if known_hints else None,
                            "priced_count": len(known_hints), "selected_count": len(hints), "items": hints, "note": ORIENTATION_NOTE},
            "methodology": "Суммы взяты из сохранённых условий действующих предложений и включают сбор заказчика. Все подтверждённые сделки и живые удержания учтены полностью. Конкурирующие предложения без выбора не складываются. Остаток — бюджет минус подтверждённые сделки и включённые предложения; ориентиры в него не вычитаются. Это не баланс оплат или возвратов."}
