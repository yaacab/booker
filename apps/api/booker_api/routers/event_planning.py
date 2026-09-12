from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import get_db
from booker_api.event_planning import selection_orientation
from booker_api.rate_limit import analytics_limiter, client_key
from booker_api.security import audit

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
