import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_planning import selection_orientation
from booker_api.matching import MatchingContext, clean_selection
from booker_api.models import Booking, Event, EventPlan, User
from booker_api.rate_limit import analytics_limiter, client_key, upload_limiter
from booker_api.security import (
    audit,
    aware,
    current_user,
    now,
    require_org_member,
    require_org_writer,
)

router = APIRouter(tags=["event planning"])


class PlanningSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: Literal["artist", "venue"]
    resource_id: UUID


class SelectionEstimateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[PlanningSelection] = Field(default_factory=list, max_length=30)


@router.post("/event-studio/estimate")
def estimate_selection(body: SelectionEstimateIn, request: Request, db: Session = Depends(get_db)):
    if not settings.smart_matching:
        raise HTTPException(503, "Расчёт ориентира временно недоступен")
    analytics_limiter.check(client_key(request, "event-estimate"))
    result = selection_orientation(db, [s.model_dump(mode="json") for s in body.selections])
    audit(db, actor_user_id=None, action="event.estimate_viewed", entity_type="event_studio", entity_id="preview",
          payload={"selected_count": result["selected_count"], "priced_count": result["priced_count"], "state": result["state"]})
    db.commit()
    return result


class EventPlanSelection(PlanningSelection):
    requirement_id: UUID
    position: int = Field(strict=True, ge=0, le=19)
    hall_id: UUID | None = None


class EventPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(strict=True, ge=0)
    expected_context: str = Field(min_length=64, max_length=64)
    selections: list[EventPlanSelection] = Field(default_factory=list, max_length=600)


class PlanningContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context: str = Field(min_length=64, max_length=64)
    ends_at: datetime | None = None
    budget_rub: int | None = Field(default=None, strict=True, ge=0, le=1_000_000_000)


def planning_event(db, user, event_id, writer=False):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Событие не найдено")
    member = (require_org_writer if writer else require_org_member)(db, user, event.organization_id)
    if not settings.smart_matching:
        raise HTTPException(503, "Подбор состава временно недоступен")
    return event, member


def matching_payload(ctx, member):
    result = ctx.payload()
    result["can_manage"] = member.role in {"owner", "admin", "manager"}
    result["can_adjust_end"] = not ctx.db.query(Booking).filter(Booking.event_id == ctx.event.id, Booking.status != "Cancelled").first()
    return result


@router.get("/events/{event_id}/matching")
def event_matching(event_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, member = planning_event(db, user, event_id)
    analytics_limiter.check(f"event-matching:{user.id}")
    result = matching_payload(MatchingContext(db, event), member)
    audit(db, actor_user_id=user.id, action="event.matching_viewed", entity_type="event", entity_id=event.id,
          payload={"state": result["state"], "required_positions": result["current"]["required_total"]})
    db.commit()
    return result


@router.put("/events/{event_id}/plan")
def save_event_plan(event_id: str, body: EventPlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, member = planning_event(db, user, event_id, writer=True)
    upload_limiter.check(f"event-plan:{user.id}")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    db.refresh(event)
    ctx = MatchingContext(db, event)
    if body.expected_context != ctx.context_token:
        raise HTTPException(409, "Параметры или роли события изменились. Обновите подбор")
    selections = sorted([clean_selection(i.model_dump(mode="json")) for i in body.selections], key=lambda i: (i["requirement_id"], i["position"]))
    old = sorted(ctx.saved, key=lambda i: (i["requirement_id"], i["position"]))
    if selections == old and body.expected_revision <= ctx.revision:
        return {**matching_payload(ctx, member), "reused": True}
    if body.expected_revision != ctx.revision:
        raise HTTPException(409, "Предварительный состав уже изменён. Загрузите актуальную версию")
    if not ctx.window_known:
        raise HTTPException(409, "Укажите будущее окно события до выбора участников")
    checked = ctx.evaluate(selections)
    if checked["problems"]:
        raise HTTPException(409, "; ".join(checked["problems"]))
    row = ctx.plan or EventPlan(event_id=event.id, revision=0)
    if not ctx.plan:
        db.add(row)
    row.revision += 1
    row.selections_json = json.dumps(selections, ensure_ascii=False, sort_keys=True)
    row.updated_at = now()
    audit(db, actor_user_id=user.id, action="event.plan_updated", entity_type="event", entity_id=event.id,
          payload={"revision": row.revision, "selected_count": len(selections)})
    db.commit()
    return matching_payload(MatchingContext(db, event), member)


@router.patch("/events/{event_id}/planning-context")
def update_planning_context(event_id: str, body: PlanningContextIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event, member = planning_event(db, user, event_id, writer=True)
    upload_limiter.check(f"event-context:{user.id}")
    db.execute(update(Event).where(Event.id == event.id).values(title=Event.title))
    db.refresh(event)
    ctx = MatchingContext(db, event)
    if body.expected_context != ctx.context_token:
        raise HTTPException(409, "Параметры события изменились. Обновите страницу")
    changed = []
    if "ends_at" in body.model_fields_set and (aware(body.ends_at) if body.ends_at else None) != (aware(event.ends_at) if event.ends_at else None):
        if db.query(Booking).filter(Booking.event_id == event.id, Booking.status != "Cancelled").first():
            raise HTTPException(409, "Окно уже используется в сделке. Согласуйте его изменение с участниками сделки")
        if body.ends_at and aware(body.ends_at) <= aware(event.event_date):
            raise HTTPException(422, "Окончание должно быть позже начала события")
        event.ends_at = aware(body.ends_at) if body.ends_at else None
        changed.append("ends_at")
    if "budget_rub" in body.model_fields_set and body.budget_rub != event.budget_rub:
        event.budget_rub = body.budget_rub
        changed.append("budget_rub")
    if changed:
        audit(db, actor_user_id=user.id, action="event.planning_updated", entity_type="event", entity_id=event.id, payload={"fields": changed})
        db.commit()
    return matching_payload(MatchingContext(db, event), member)
