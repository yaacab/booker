"""Guest capabilities are separate from account sessions and scoped to one shortlist."""
import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import update

from booker_api.config import settings
from booker_api.models import Artist, SharedShortlist, ShortlistFeedback, ShortlistGuest, Venue
from booker_api.rate_limit import analytics_limiter, messaging_limiter
from booker_api.security import aware, now


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def limit(request, *, write=False):
    # The direct peer cannot be spoofed with arbitrary X-Real-IP headers.
    peer = request.client.host if request.client else "unknown"
    (messaging_limiter if write else analytics_limiter).check(f"shortlist:{peer}")


def public_text(value):
    value = value.strip()
    if re.search(r"https?://|www\.|\S+@\S+|(?:\+?\d[\s().-]*){7,}", value, re.IGNORECASE):
        raise ValueError("Не добавляйте контакты и внешние ссылки в обсуждение")
    return value


def active_share(db, token, *, lock=False, write=False):
    if len(token) > 64:
        raise HTTPException(404, "Ссылка недоступна")
    if lock:
        db.execute(update(SharedShortlist).where(SharedShortlist.token == token).values(title=SharedShortlist.title))
    row = db.query(SharedShortlist).filter_by(token=token).populate_existing().one_or_none()
    if not row or row.revoked_at or aware(row.expires_at) <= now():
        raise HTTPException(404, "Ссылка недоступна")
    if write and not settings.collaborative_events:
        raise HTTPException(503, "Совместные обсуждения временно отключены")
    if write and not row.collaborative:
        raise HTTPException(403, "Эта подборка доступна только для чтения")
    return row


def guest_for(db, row, secret, *, required=False):
    guest = None
    if secret and re.fullmatch(r"[a-f0-9]{64}", secret):
        guest = db.query(ShortlistGuest).filter_by(shortlist_id=row.id, secret_hash=digest(secret)).one_or_none()
    if required and not guest:
        raise HTTPException(401, "Представьтесь, чтобы участвовать в этой подборке")
    return guest


def visible_item(db, kind, item):
    profile = db.get(Artist if kind == "artist" else Venue, item.target_id)
    return profile and (kind == "artist" or profile.moderation_status == "published")


def shared_payload(db, row, guest=None):
    pairs = db.query(ShortlistFeedback, ShortlistGuest).join(ShortlistGuest, ShortlistFeedback.guest_id == ShortlistGuest.id).filter(ShortlistGuest.shortlist_id == row.id).all()
    items = []
    for item in sorted(row.items, key=lambda i: i.sort_order):
        if not visible_item(db, row.target_type, item):
            continue
        feedback = [(f, g) for f, g in pairs if f.item_id == item.id]
        mine = next((f for f, g in feedback if guest and g.id == guest.id), None)
        items.append({"target_id": item.target_id, "name": item.name, "city": item.city, "summary": item.summary,
            "profile_path": f"/{'artists' if row.target_type == 'artist' else 'venues'}/{item.target_id}",
            "counts": {reaction: sum(f.reaction == reaction for f, _ in feedback) for reaction in ("vote", "favorite", "reject")},
            "feedback": [{"name": g.display_name, "reaction": f.reaction, "comment": f.comment} for f, g in feedback if f.reaction or f.comment],
            "mine": {"reaction": mine.reaction, "comment": mine.comment, "revision": mine.revision} if mine else {"reaction": None, "comment": "", "revision": 0}})
    return {"title": row.title, "target_type": row.target_type, "expires_at": row.expires_at.isoformat(),
        "collaborative": row.collaborative and settings.collaborative_events, "guest_name": guest.display_name if guest else None,
        "items": items, "robots": "noindex",
        "note": "Гостевые имена не проверены. Это мнения участников подборки, а не отзывы о завершённых сделках или рейтинг исполнителей."}
