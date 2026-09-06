"""Organic promo funnel — audit-only events, no new tables (W3-PROMO)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.security import audit

router = APIRouter(prefix="/promo", tags=["promo"])

ALLOWED_PROMO_EVENTS: frozenset[str] = frozenset(
    {
        "promo.share.view",
        "promo.profile.open",
        "promo.link.copy",
        "promo.qr.display",
    }
)


class PromoEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
    profile_kind: str = Field(pattern=r"^(artist|venue)$")
    profile_id: str = Field(min_length=1, max_length=64)
    medium: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=64)


@router.post("/events")
def record_promo_event(
    body: PromoEventIn,
    request: Request,
    db: Session = Depends(get_db),
):
    analytics_limiter.check(client_key(request, "promo"))
    if body.name not in ALLOWED_PROMO_EVENTS:
        return {"ok": False, "ignored": True}
    audit(
        db,
        actor_user_id=None,
        action="promo.event",
        entity_type=body.profile_kind,
        entity_id=body.profile_id,
        payload={
            "name": body.name,
            "medium": body.medium,
            "source": body.source,
        },
    )
    db.commit()
    return {"ok": True, "id": str(uuid4())}
