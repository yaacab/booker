"""Non-contractual event planning from published facts, never from invented prices."""
from sqlalchemy.orm import Session

from booker_api.models import Artist, ArtistTariff, Venue, VenueTariff

ORIENTATION_NOTE = "Ориентировочная стоимость. Итоговые условия формируются только после предложений участников."


def tariff_range(tariffs) -> dict:
    # Historic imports may contain absent/invalid amounts. Do not silently turn them into zero.
    rows = [t for t in tariffs if type(t.honorarium_rub) is int and 0 <= t.honorarium_rub <= 1_000_000_000]
    return {"min_rub": min((t.honorarium_rub for t in rows), default=None),
            "max_rub": max((t.honorarium_rub for t in rows), default=None),
            "sources": [{"tariff_id": t.id, "title": t.title, "honorarium_rub": t.honorarium_rub,
                         "hours": getattr(t, "hours", None)} for t in sorted(rows, key=lambda t: (t.honorarium_rub, t.id))]}


def selection_orientation(db: Session, selections: list[dict]) -> dict:
    """Sum actual public package ranges; missing prices remain missing, even for a paid profile."""
    items, seen = [], set()
    for selection in selections:
        kind, target_id = selection["resource_type"], str(selection["resource_id"])
        if (kind, target_id) in seen:
            continue
        seen.add((kind, target_id))
        profile = db.get(Artist if kind == "artist" else Venue, target_id)
        if not profile or (kind == "venue" and profile.moderation_status != "published"):
            # Same public shape for a missing or hidden profile; do not expose hidden tariffs/name.
            items.append({"resource_type": kind, "resource_id": target_id, "name": None, "state": "unavailable",
                          "min_rub": None, "max_rub": None, "sources": []})
            continue
        tariffs = db.query(ArtistTariff).filter_by(artist_id=target_id).all() if kind == "artist" else db.query(VenueTariff).filter_by(venue_id=target_id).all()
        prices = tariff_range(tariffs)
        items.append({"resource_type": kind, "resource_id": target_id, "name": profile.name,
                      "state": "known" if prices["min_rub"] is not None else "unknown", **prices})
    known = [item for item in items if item["state"] == "known"]
    state = "empty" if not items else "unknown" if not known else "complete" if len(known) == len(items) else "partial"
    return {"state": state, "currency": "RUB", "basis": "published_honorarium_packages", "is_orientation": True,
            "min_rub": sum(item["min_rub"] for item in known) if known else None,
            "max_rub": sum(item["max_rub"] for item in known) if known else None,
            "selected_count": len(items), "priced_count": len(known), "items": items,
            "coverage_label": f"Стоимость указана у {len(known)} из {len(items)} участников.",
            "note": ORIENTATION_NOTE,
            "methodology": "Диапазон суммы опубликованных пакетов услуг, без сервисного сбора заказчика. Пакеты могут отличаться составом и длительностью; цена не масштабируется по времени. При неполных данных показана только известная часть. Расчёт не подтверждает доступность или совместимость."}
