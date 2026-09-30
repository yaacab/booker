import csv
import io
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request as HttpRequest
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from booker_api.commerce.entitlements import require_feature
from booker_api.commerce.orders import lock_organization
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.growth.service import growth_summary, record_loss, record_signal
from booker_api.models import Event, Request, User
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.security import (
    audit,
    authenticate_token,
    bearer,
    current_user,
    membership,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["growth"])


class SignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: Literal["artist", "venue"]
    target_id: UUID
    kind: Literal["impression", "profile_view"]
    visitor_id: UUID


class LossInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal[
        "price", "customer_selected_another", "event_cancelled", "supplier_declined", "unknown"
    ]


def gate():
    if not settings.artist_growth:
        raise HTTPException(404, "Аналитика роста пока недоступна")


@router.post("/discovery/signals")
def post_signal(
    body: SignalInput,
    request: HttpRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    gate()
    analytics_limiter.check(client_key(request, "discovery"))
    actor = authenticate_token(db, credentials.credentials)[0] if credentials else None
    record_signal(
        db,
        body.target_type,
        str(body.target_id),
        body.kind,
        str(body.visitor_id),
        actor.id if actor else None,
    )
    db.commit()
    return {"ok": True}


@router.get("/organizations/{org_id}/growth")
def get_growth(
    org_id: str,
    days: int = Query(30, ge=7, le=365),
    target_id: str | None = Query(None, max_length=36),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    gate()
    require_org_member(db, user, org_id)
    require_feature(db, org_id, "analytics.basic")
    return growth_summary(db, org_id, days, target_id)


@router.get("/organizations/{org_id}/growth/export")
def export_growth(
    org_id: str,
    days: int = Query(30, ge=7, le=365),
    target_id: str | None = Query(None, max_length=36),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    gate()
    require_org_member(db, user, org_id)
    require_feature(db, org_id, "export.analytics")
    data = growth_summary(db, org_id, days, target_id)
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow(["metric", "value", "days"])
    for key, value in data["funnel"].items():
        writer.writerow([key, value, days])
    writer.writerow(["confirmed_honorarium_rub", data["confirmed_honorarium_rub"], days])
    audit(
        db,
        actor_user_id=user.id,
        action="growth.exported",
        entity_type="organization",
        entity_id=org_id,
        payload={"days": days, "profile_id": target_id},
    )
    db.commit()
    return Response(
        content.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="booker-growth.csv"'},
    )


@router.post("/requests/{request_id}/loss-reason")
def post_loss(
    request_id: str,
    body: LossInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Recording a real reason is available to Free; detailed loss analytics is paid.
    gate()
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    event = db.get(Event, req.event_id)
    if membership(db, user.id, event.organization_id):
        require_org_writer(db, user, event.organization_id)
        side = "customer"
    else:
        require_org_writer(db, user, req.supplier_org_id)
        side = "supplier"
    lock_organization(db, req.supplier_org_id)
    record_loss(db, req, body.reason, user.id, side)
    db.commit()
    return {"ok": True, "reason": body.reason}
