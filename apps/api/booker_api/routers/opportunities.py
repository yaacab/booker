import json
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request as HttpRequest
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from booker_api.commerce.entitlements import require_feature
from booker_api.commerce.orders import lock_organization
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.models import OpportunityFilter, Organization, User
from booker_api.opportunities import feed, profiles_for
from booker_api.rate_limit import client_key, messaging_limiter
from booker_api.security import audit, current_user, now, require_org_member, require_org_writer

router = APIRouter(tags=["opportunities"])


class OpportunityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int | None = Field(None, ge=1, le=200)
    target_id: UUID | None = None
    city: str | None = Field(None, max_length=128)
    date_from: date | None = None
    date_to: date | None = None
    budget_min_rub: int | None = Field(None, ge=0, le=1_000_000_000)
    minimum_score: int | None = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Конечная дата должна быть не раньше начальной")
        return self


class FilterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    query: OpportunityQuery
    instant_alerts: bool = False
    consent: bool = False
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


def organization(db, user, org_id, writer=False):
    if not settings.opportunities:
        raise HTTPException(404, "Подходящие заказы пока недоступны")
    (require_org_writer if writer else require_org_member)(db, user, org_id)
    org = db.get(Organization, org_id)
    if org.kind not in {"artist", "venue"}:
        raise HTTPException(422, "Раздел доступен исполнителям и площадкам")
    return org


def validate_query(db, org, query):
    if query.get("target_id") and query["target_id"] not in {p.id for p in profiles_for(db, org)}:
        raise HTTPException(403, "Нет доступа к выбранному профилю")
    if any(
        value is not None and value != ""
        for key, value in query.items()
        if key not in {"target_id", "page"}
    ):
        require_feature(db, org.id, "opportunities.filters")


def filter_payload(saved):
    return {
        "id": saved.id,
        "name": saved.name,
        "query": json.loads(saved.query_json),
        "instant_alerts": saved.instant_alerts,
        "active": saved.active,
    }


@router.get("/organizations/{org_id}/opportunities")
def get_opportunities(
    org_id: str,
    query: Annotated[OpportunityQuery, Query()],
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    org = organization(db, user, org_id)
    params = query.model_dump(mode="json", exclude_none=True)
    validate_query(db, org, params)
    return feed(db, org, params)


@router.get("/organizations/{org_id}/opportunity-filters")
def get_filters(org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization(db, user, org_id)
    rows = (
        db.query(OpportunityFilter)
        .filter_by(organization_id=org_id, user_id=user.id, active=True)
        .order_by(OpportunityFilter.created_at)
        .all()
    )
    # Retain visibility and deletion after downgrade; applying paid filters is still checked.
    return {"items": [filter_payload(row) for row in rows]}


@router.post("/organizations/{org_id}/opportunity-filters")
def create_filter(
    org_id: str,
    body: FilterInput,
    request: HttpRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    org = organization(db, user, org_id, writer=True)
    require_feature(db, org_id, "opportunities.filters")
    messaging_limiter.check(client_key(request, "opportunity-filter"))
    params = body.query.model_dump(mode="json", exclude_none=True)
    validate_query(db, org, params)
    if body.instant_alerts:
        require_feature(db, org_id, "opportunities.instant_alerts")
        if not body.consent:
            raise HTTPException(422, "Подтвердите согласие на уведомления по этому поиску")
    lock_organization(db, org_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Введите название поиска")
    query_json = json.dumps(params, sort_keys=True)
    existing = (
        db.query(OpportunityFilter)
        .filter_by(organization_id=org_id, idempotency_key=body.idempotency_key)
        .first()
    )
    if existing:
        if (
            existing.user_id != user.id
            or existing.name != name
            or existing.query_json != query_json
            or existing.instant_alerts != body.instant_alerts
        ):
            raise HTTPException(409, "Ключ уже использован для другого поиска")
        return filter_payload(existing)
    if (
        db.query(OpportunityFilter)
        .filter_by(organization_id=org_id, user_id=user.id, active=True)
        .count()
        >= 20
    ):
        raise HTTPException(409, "Можно сохранить до 20 поисков")
    saved = OpportunityFilter(
        organization_id=org_id,
        user_id=user.id,
        name=name,
        query_json=query_json,
        idempotency_key=body.idempotency_key,
        instant_alerts=body.instant_alerts,
        consent_at=now() if body.instant_alerts else None,
    )
    db.add(saved)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="opportunity.filter_saved",
        entity_type="opportunity_filter",
        entity_id=saved.id,
        payload={
            "organization_id": org_id,
            "instant_alerts": body.instant_alerts,
            "explicit_consent": body.consent,
        },
    )
    db.commit()
    return filter_payload(saved)


@router.delete("/opportunity-filters/{filter_id}")
def delete_filter(
    filter_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    saved = db.get(OpportunityFilter, filter_id)
    if not saved or saved.user_id != user.id:
        raise HTTPException(404, "Сохранённый поиск не найден")
    require_org_member(db, user, saved.organization_id)
    if saved.active:
        saved.active = False
        saved.instant_alerts = False
        audit(
            db,
            actor_user_id=user.id,
            action="opportunity.filter_removed",
            entity_type="opportunity_filter",
            entity_id=saved.id,
        )
    db.commit()
    return {"ok": True}
