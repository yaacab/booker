from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import User
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.schemas import ClientEventIn
from booker_api.security import audit, current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])

ALLOWED_CLIENT_EVENTS = frozenset(
    {
        "page.view",
        "event.studio.started",
        "event.studio.completed",
        "search.performed",
        "deal.room.opened",
    }
)


@router.post("/events")
def record_client_event(
    body: ClientEventIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    analytics_limiter.check(client_key(request, "analytics"))
    if body.name not in ALLOWED_CLIENT_EVENTS:
        return {"ok": False, "ignored": True}
    audit(
        db,
        actor_user_id=user.id,
        action="client.event",
        entity_type="client_event",
        entity_id=body.name,
        payload={"name": body.name, "properties": body.properties},
    )
    db.commit()
    return {"ok": True}
