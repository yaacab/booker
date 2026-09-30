"""Explainable draft lineups. Candidate selection never creates an offer or a reservation."""
import copy
import hashlib
import json
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from booker_api.compatibility import (
    assess_compatibility,
    event_slot_ids,
    hall_facts,
    resource_available,
)
from booker_api.composition import ROLE_LABEL, requirement_payload
from booker_api.event_planning import ORIENTATION_NOTE, tariff_range
from booker_api.models import (
    Artist,
    ArtistTariff,
    AvailabilitySlot,
    Event,
    EventPlan,
    EventTeamRequirement,
    Venue,
    VenueHall,
    VenueTariff,
)
from booker_api.presentation import presentation_data
from booker_api.security import aware, now

MODES = [
    ("economy", "Экономный", "Обязательные роли. Сначала меньший опубликованный стартовый тариф, затем меньше неуточнённых условий."),
    ("balanced", "Оптимальный", "Обязательные роли. Сначала меньше неуточнённых технических условий, затем меньший опубликованный тариф."),
    ("expanded", "Расширенный", "Все указанные роли, включая необязательные. Сначала подробнее заполненные программа и портфолио, затем технические условия и тариф."),
]


def selection_key(item):
    return f"{item['resource_type']}:{item['resource_id']}:{item.get('hall_id') or ''}"


def clean_selection(item):
    return {k: item.get(k) for k in ("requirement_id", "position", "resource_type", "resource_id", "hall_id")}


class MatchingContext:
    def __init__(self, db: Session, event: Event):
        self.db, self.event = db, event
        self.requirements = db.query(EventTeamRequirement).filter_by(event_id=event.id).order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id).all()
        self.by_requirement = {r.id: r for r in self.requirements}
        self.plan = db.get(EventPlan, event.id)
        self.revision = self.plan.revision if self.plan else 0
        self.saved = json.loads(self.plan.selections_json) if self.plan else []
        self.context_token = hashlib.sha256(json.dumps({"event": [event.city, str(event.event_date), str(event.ends_at), event.guest_count, event.budget_rub],
            "roles": [requirement_payload(r) for r in self.requirements]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.start = aware(event.event_date)
        self.end = aware(event.ends_at) if event.ends_at else None
        self.window_known = bool(self.end and self.end > self.start and self.end > now())
        self.own_slots = event_slot_ids(db, event.id)
        self.slots = defaultdict(list)
        self.pool = defaultdict(list)
        self.candidates = {}
        self.artists = {}
        self.venues = {}
        self.halls = {}
        self.presentation = {}
        self.technical = {}
        self.pairs = {}
        if not self.window_known:
            return
        codes = {r.category_code for r in self.requirements if r.category_code != "venue"}
        artists = db.query(Artist).filter(Artist.category.in_(codes)).all() if codes else []
        for artist in artists:
            data = presentation_data(db, artist)[1]
            if event.city.strip().casefold() not in {artist.city.strip().casefold(), *(c.strip().casefold() for c in data.get("travel_cities", []))}:
                continue
            self.artists[artist.id], self.presentation[artist.id] = artist, data
        venues = [v for v in db.query(Venue).filter_by(moderation_status="published", is_claimed=True, availability_mode="owner").all() if v.city.strip().casefold() == event.city.strip().casefold()] if any(r.category_code == "venue" for r in self.requirements) else []
        self.venues = {v.id: v for v in venues}
        halls = db.query(VenueHall).filter(VenueHall.venue_id.in_(self.venues), VenueHall.capacity >= event.guest_count).all() if venues else []
        self.halls = {h.id: h for h in halls}
        ids = [*self.artists, *self.halls]
        for slot in db.query(AvailabilitySlot).filter(AvailabilitySlot.resource_id.in_(ids)).all() if ids else []:
            self.slots[(slot.resource_type, slot.resource_id)].append(slot)
        artist_tariffs, venue_tariffs = defaultdict(list), defaultdict(list)
        for t in db.query(ArtistTariff).filter(ArtistTariff.artist_id.in_(self.artists)).all() if self.artists else []:
            artist_tariffs[t.artist_id].append(t)
        for t in db.query(VenueTariff).filter(VenueTariff.venue_id.in_(self.venues)).all() if self.venues else []:
            venue_tariffs[t.venue_id].append(t)
        for artist_id, artist in self.artists.items():
            data = self.presentation[artist_id]
            tech = data.get("technical") or {}
            before, after = tech.get("setup_minutes"), tech.get("teardown_minutes")
            if not self.available("artist", artist_id, before=before or 0, after=after or 0):
                continue
            portfolio = [label for key, label in [("format", "формат"), ("lineup", "состав"), ("program", "программа"), ("primary_video_url", "основное видео"), ("gallery", "галерея"), ("links", "аудио/видео")] if data.get(key)]
            warnings = ["Монтаж или демонтаж не уточнён"] if before is None or after is None else []
            item = {"resource_type": "artist", "resource_id": artist.id, "hall_id": None, "name": artist.name,
                    "category": artist.category, "profile_href": f"/artists/{artist.id}", "prices": tariff_range(artist_tariffs[artist_id]),
                    "reasons": [f"Роль: {ROLE_LABEL.get(artist.category, 'из состава события')}", f"Город или заявленный выезд: {event.city}", "Календарь покрывает всё окно события"],
                    "warnings": warnings, "presentation_facts": portfolio,
                    "technical_unknown": sum(value is None for value in tech.values()), "compatibility": None}
            self.add_candidate(item)
        for hall in halls:
            if not self.available("hall", hall.id):
                continue
            venue = self.venues[hall.venue_id]
            self.technical[hall.id] = hall_facts(db, hall)
            facts = self.technical[hall.id][1]
            item = {"resource_type": "venue", "resource_id": venue.id, "hall_id": hall.id,
                    "name": f"{venue.name} · {hall.name}", "category": "venue", "profile_href": f"/venues/{venue.id}",
                    "prices": tariff_range(venue_tariffs[venue.id]), "reasons": [f"Город: {venue.city}", f"Вместимость зала: {hall.capacity}; гостей: {event.guest_count}", "Календарь владельца покрывает всё окно события"],
                    "warnings": ["Ограничения зала не уточнены"] if facts.get("restrictions") is None else [facts["restrictions"]] if facts["restrictions"] else [],
                    "presentation_facts": [], "technical_unknown": sum(v is None for v in facts.values()), "compatibility": None}
            self.add_candidate(item)

    def available(self, kind, target_id, **kwargs):
        return resource_available(self.db, kind, target_id, self.start, self.end,
            own_slot_ids=self.own_slots, slots=self.slots[(kind, target_id)], **kwargs)

    def add_candidate(self, item):
        item["candidate_key"] = selection_key(item)
        self.candidates[item["candidate_key"]] = item
        self.pool[item["category"]].append(item)

    def with_halls(self, item, halls):
        result = copy.deepcopy(item)
        if item["resource_type"] != "artist":
            return result
        if not halls:
            result["warnings"].append("Площадка не выбрана: совместимость райдера не проверена")
            return result
        pairs = []
        for venue_item in halls:
            key = (item["resource_id"], venue_item["hall_id"])
            if key not in self.pairs:
                self.pairs[key] = assess_compatibility(self.db, artist=self.artists[key[0]], venue=self.venues[venue_item["resource_id"]], hall=self.halls[key[1]],
                    starts_at=self.start, ends_at=self.end, guest_count=self.event.guest_count, event_city=self.event.city,
                    own_slot_ids=self.own_slots, artist_data=self.presentation[key[0]], hall_data=self.technical[key[1]], slot_cache=self.slots)
            pairs.append(self.pairs[key])
        fits = [p for p in pairs if p["status"] != "incompatible"]
        if not fits:
            return None
        pair = min(fits, key=lambda p: (len(p["to_resolve"]), p["hall"]["id"]))
        result["compatibility"] = {k: pair[k] for k in ("status", "status_label", "score", "hall", "to_resolve")}
        result["reasons"].append(f"Райдер сопоставлен с залом «{pair['hall']['name']}»; известных несоответствий нет")
        result["warnings"] = list(dict.fromkeys([*result["warnings"], *(f"{c['label']}: {c['explanation']}" for c in pair["to_resolve"])]))
        result["technical_unknown"] = len(pair["to_resolve"])
        return result

    @staticmethod
    def rank(item, mode):
        price = item["prices"]["min_rub"]
        money = (price is None, price or 0)
        unknown = item["technical_unknown"] + len(item["warnings"])
        portfolio = -len(item["presentation_facts"])
        if mode == "economy":
            return (*money, unknown, item["candidate_key"])
        if mode == "balanced":
            return (unknown, *money, item["candidate_key"])
        return (portfolio, unknown, *money, item["candidate_key"])

    def units(self, include_optional=True):
        return [{"requirement_id": r.id, "position": i, "category": r.category_code,
                 "label": r.role_label or r.category_code, "required": r.required}
                for r in self.requirements if include_optional or r.required for i in range(r.qty)]

    def orientation(self, items):
        repeated_venues = Counter(i["resource_id"] for i in items if i["resource_type"] == "venue")
        known = [i for i in items if i["prices"]["min_rub"] is not None and not (i["resource_type"] == "venue" and repeated_venues[i["resource_id"]] > 1)]
        return {"state": "empty" if not items else "unknown" if not known else "complete" if len(known) == len(items) else "partial",
                "min_rub": sum(i["prices"]["min_rub"] for i in known) if known else None,
                "max_rub": sum(i["prices"]["max_rub"] for i in known) if known else None,
                "priced_count": len(known), "selected_count": len(items), "currency": "RUB", "note": ORIENTATION_NOTE,
                "methodology": "Диапазон опубликованных пакетов до сервисного сбора. Неизвестные цены не входят в сумму; длительность не умножает тариф. Стоимость нескольких залов одной площадки требует отдельного предложения."}

    def evaluate(self, selections):
        units = {(u["requirement_id"], u["position"]): u for u in self.units()}
        entries, problems, used_units, used_profiles = [], [], set(), set()
        for raw in selections:
            clean = clean_selection(raw)
            unit_key = (clean["requirement_id"], clean["position"])
            unit = units.get(unit_key)
            candidate = self.candidates.get(selection_key(clean))
            if not unit or unit_key in used_units:
                problems.append("Позиция состава удалена, изменилась или выбрана дважды")
            elif not candidate or candidate["category"] != unit["category"]:
                problems.append(f"{unit['label']}: профиль больше не соответствует городу, категории, вместимости или окну события")
            elif candidate["candidate_key"] in used_profiles:
                problems.append("Один артист или зал выбран для нескольких одновременных позиций")
            else:
                entries.append({**candidate, **clean, "role_label": unit["label"], "required": unit["required"]})
                used_units.add(unit_key); used_profiles.add(candidate["candidate_key"])
        halls = [i for i in entries if i["resource_type"] == "venue"]
        checked = []
        for item in entries:
            pair = self.with_halls(item, halls)
            if pair is None:
                problems.append(f"{item['role_label']}: требования артиста несовместимы с выбранными залами")
            else:
                checked.append(pair)
        filled = {(i["requirement_id"], i["position"]) for i in checked}
        missing = [u for key, u in units.items() if key not in filled]
        return {"selections": checked, "problems": list(dict.fromkeys(problems)), "uncovered": missing,
                "orientation": self.orientation(checked), "required_total": sum(u["required"] for u in units.values()),
                "required_covered": sum(i["required"] for i in checked), "optional_covered": sum(not i["required"] for i in checked)}

    def variants(self):
        variants = []
        for mode, title, explanation in MODES:
            units = self.units(include_optional=mode == "expanded")
            venue_units = [u for u in units if u["category"] == "venue"]
            anchors = self.pool["venue"] if venue_units and self.pool["venue"] else [None]
            options = []
            for anchor in anchors:
                selected, used = [], set()
                halls = sorted(self.pool["venue"], key=lambda i: self.rank(i, mode))
                if anchor:
                    halls = [anchor, *(h for h in halls if h["candidate_key"] != anchor["candidate_key"])]
                for unit, candidate in zip(venue_units, halls):
                    selected.append({**candidate, "requirement_id": unit["requirement_id"], "position": unit["position"]})
                    used.add(candidate["candidate_key"])
                chosen_halls = list(selected)
                for unit in (u for u in units if u["category"] != "venue"):
                    candidates = [self.with_halls(c, chosen_halls) for c in self.pool[unit["category"]] if c["candidate_key"] not in used]
                    fits = [c for c in candidates if c is not None]
                    if not fits:
                        continue
                    candidate = min(fits, key=lambda c: self.rank(c, mode))
                    selected.append({**candidate, "requirement_id": unit["requirement_id"], "position": unit["position"]})
                    used.add(candidate["candidate_key"])
                result = self.evaluate(selected)
                items = result["selections"]
                missing = result["required_total"] - result["required_covered"]
                orientation = result["orientation"]
                unknown_price = orientation["selected_count"] - orientation["priced_count"]
                cost = orientation["min_rub"] or 0
                unknown = sum(i["technical_unknown"] + len(i["warnings"]) for i in items)
                portfolio = -sum(len(i["presentation_facts"]) for i in items)
                rank = (missing, unknown_price, cost, unknown) if mode == "economy" else (missing, unknown, unknown_price, cost) if mode == "balanced" else (missing, -result["optional_covered"], portfolio, unknown, unknown_price, cost)
                options.append((rank, result))
            result = min(options, key=lambda r: r[0])[1]
            variants.append({"code": mode, "title": title, "explanation": explanation, **result})
        return variants

    def payload(self):
        variants = self.variants()
        signatures = [tuple(sorted(selection_key(i) for i in v["selections"])) for v in variants]
        state = "needs_window" if not self.window_known else "needs_roles" if not self.requirements else "ready"
        return {"event_id": self.event.id, "event_title": self.event.title, "city": self.event.city,
                "starts_at": self.start, "ends_at": self.end, "guest_count": self.event.guest_count,
                "declared_budget": self.event.budget_rub, "revision": self.revision, "context_token": self.context_token,
                "state": state, "variants": variants, "current": self.evaluate(self.saved),
                "saved_selections": self.saved, "requirements": [requirement_payload(r) for r in self.requirements],
                "candidates": {k: sorted(v, key=lambda i: self.rank(i, "balanced")) for k, v in self.pool.items()},
                "variants_overlap": len(set(signatures)) < len(signatures),
                "note": "Предварительный состав не удерживает дату и не меняет отправленные заявки, офферы или сделки. Доступность перепроверяется при сохранении и бронировании. Подписка и продвижение не влияют на подбор."}
