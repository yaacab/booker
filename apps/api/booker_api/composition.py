"""Состав события: requirements + мост из Event.notes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.models import CatalogCategory, Event, EventTeamRequirement, Request

PILOT_CATEGORIES = [
    ("dj", "DJ", "music", 10),
    ("host", "Ведущий", "speech", 20),
    ("cover", "Кавер", "music", 30),
    ("photo", "Фотограф", "content", 40),
    ("makeup", "Визажист", "prep", 50),
    ("decor", "Декоратор", "production", 60),
    ("catering", "Кейтеринг", "food", 70),
    ("venue", "Площадка", "space", 80),
]

ROLE_LABEL = {code: title for code, title, _g, _s in PILOT_CATEGORIES}

KIND_ALIASES = {"performer": "artist", "исполнитель": "artist"}
ALLOWED_ORG_KINDS = {"customer", "artist", "venue"}
ALLOWED_ROLES = {"owner", "admin", "manager", "viewer"}
WRITE_ROLES = {"owner", "admin", "manager"}


def normalize_kind(kind: str) -> str:
    raw = (kind or "").strip().lower()
    return KIND_ALIASES.get(raw, raw)


def seed_categories(db: Session) -> None:
    existing = {c.code for c in db.query(CatalogCategory).all()}
    for code, title, group, order in PILOT_CATEGORIES:
        if code in existing:
            continue
        db.add(
            CatalogCategory(
                code=code,
                title=title,
                group_code=group,
                published=True,
                sort_order=order,
            )
        )
    db.flush()


def parse_notes(notes: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for chunk in (notes or "").split(";"):
        part = chunk.strip()
        if not part or ":" not in part:
            continue
        key, _, val = part.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key == "артист":
            if val in {"пока не знаю", "unknown", ""}:
                continue
            code = val if val in ROLE_LABEL else "dj"
            if code not in seen:
                items.append({"category_code": code, "role_label": ROLE_LABEL.get(code, code), "qty": 1})
                seen.add(code)
        elif key == "площадка":
            if val in {"пока не знаю", "unknown"}:
                continue
            if "venue" not in seen:
                items.append(
                    {
                        "category_code": "venue",
                        "role_label": ROLE_LABEL["venue"],
                        "qty": 1,
                        "notes": val,
                    }
                )
                seen.add("venue")
    return items


def requirement_payload(row: EventTeamRequirement) -> dict:
    return {
        "id": row.id,
        "category_code": row.category_code,
        "role_label": row.role_label or ROLE_LABEL.get(row.category_code, row.category_code),
        "qty": row.qty,
        "required": row.required,
        "status": row.status,
        "sort_order": row.sort_order,
        "notes": row.notes,
    }


def replace_requirements(db: Session, event: Event, items: list[dict]) -> list[EventTeamRequirement]:
    existing = (
        db.query(EventTeamRequirement)
        .filter(EventTeamRequirement.event_id == event.id)
        .order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id)
        .all()
    )
    by_id = {row.id: row for row in existing}
    unused = list(existing)
    rows: list[EventTeamRequirement] = []

    def take(row: EventTeamRequirement) -> EventTeamRequirement:
        unused.remove(row)
        return row

    for i, raw in enumerate(items):
        code = str(raw.get("category_code") or "").strip().lower()
        if not code:
            continue
        incoming_id = str(raw.get("id") or "").strip()
        row = None
        if incoming_id and incoming_id in by_id and by_id[incoming_id] in unused:
            row = take(by_id[incoming_id])
        else:
            for cand in unused:
                if cand.category_code == code:
                    row = take(cand)
                    break
        if row is None:
            row = EventTeamRequirement(event_id=event.id, category_code=code)
            db.add(row)
        row.category_code = code
        row.role_label = str(raw.get("role_label") or ROLE_LABEL.get(code, code))
        row.qty = max(1, int(raw.get("qty") or 1))
        row.required = bool(raw.get("required", True))
        row.status = str(raw.get("status") or getattr(row, "status", None) or "open")
        row.sort_order = int(raw["sort_order"]) if raw.get("sort_order") is not None else i
        row.notes = str(raw.get("notes") or "")
        rows.append(row)

    leftover_ids = [row.id for row in unused if row.id]
    if leftover_ids:
        db.query(Request).filter(Request.requirement_id.in_(leftover_ids)).update(
            {Request.requirement_id: None},
            synchronize_session=False,
        )
        for row in unused:
            db.delete(row)
    db.flush()
    return rows


def ensure_requirements(db: Session, event: Event, explicit: list[dict] | None = None) -> list[dict]:
    rows = (
        db.query(EventTeamRequirement)
        .filter(EventTeamRequirement.event_id == event.id)
        .order_by(EventTeamRequirement.sort_order, EventTeamRequirement.id)
        .all()
    )
    if rows:
        return [requirement_payload(r) for r in rows]
    source = explicit if explicit is not None else parse_notes(event.notes)
    if not source:
        return []
    created = replace_requirements(db, event, source)
    return [requirement_payload(r) for r in created]
