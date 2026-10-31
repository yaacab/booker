"""Saved catalog searches for logged-in customers (W3-SAVED)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from booker_api.db import get_db
from booker_api.models import Organization, SavedSearch, User
from booker_api.security import current_user, require_org_member

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])

ALLOWED_QUERY_KEYS = frozenset({"format", "city", "budget_max", "guests", "kind"})


class SavedSearchQueryParams(BaseModel):
    format: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    budget_max: int | None = Field(default=None, ge=0)
    guests: int | None = Field(default=None, ge=1)
    kind: str | None = Field(default=None, max_length=32)

    @field_validator("format", "city", "kind")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class SavedSearchIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    organization_id: str | None = None
    query_params: SavedSearchQueryParams
    notify_consent: bool = False
    consent: bool = False


class NotifyConsentPatch(BaseModel):
    notify_consent: bool
    consent: bool = False


def _resolve_org_id(
    db: Session,
    user: User,
    organization_id: str | None,
    x_booker_org: str | None,
) -> str:
    org_id = (organization_id or x_booker_org or user.active_organization_id or "").strip()
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужна организация")
    require_org_member(db, user, org_id)
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Организация не найдена")
    if org.kind != "customer" and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сохранять поиск может только заказчик")
    return org_id


def _require_notify_consent(notify_consent: bool, consent: bool) -> None:
    if notify_consent and not consent:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Для уведомлений нужно явное согласие (consent=true)",
        )


def _serialize_query_params(params: SavedSearchQueryParams) -> str:
    payload = params.model_dump(exclude_none=True)
    unknown = set(payload) - ALLOWED_QUERY_KEYS
    if unknown:
        raise HTTPException(400, f"Недопустимые параметры поиска: {', '.join(sorted(unknown))}")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _deserialize_query_params(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in ALLOWED_QUERY_KEYS if k in data and data[k] is not None}


def _search_path(params: dict) -> str:
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"/search{('?' + qs) if qs else ''}"


def _out(row: SavedSearch) -> dict:
    params = _deserialize_query_params(row.query_params_json)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "organization_id": row.organization_id,
        "name": row.name,
        "query_params": params,
        "search_path": _search_path(params),
        "notify_consent": row.notify_consent,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def list_saved_searches(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _resolve_org_id(db, user, None, x_booker_org)
    rows = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user.id, SavedSearch.organization_id == org_id)
        .order_by(SavedSearch.created_at.desc())
        .all()
    )
    return {"items": [_out(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_saved_search(
    body: SavedSearchIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    org_id = _resolve_org_id(db, user, body.organization_id, x_booker_org)
    _require_notify_consent(body.notify_consent, body.consent)
    row = SavedSearch(
        user_id=user.id,
        organization_id=org_id,
        name=body.name.strip(),
        query_params_json=_serialize_query_params(body.query_params),
        notify_consent=body.notify_consent,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/{saved_search_id}/notify-consent")
def patch_notify_consent(
    saved_search_id: str,
    body: NotifyConsentPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SavedSearch, saved_search_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сохранённый поиск не найден")
    require_org_member(db, user, row.organization_id)
    _require_notify_consent(body.notify_consent, body.consent)
    row.notify_consent = body.notify_consent
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(
    saved_search_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SavedSearch, saved_search_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сохранённый поиск не найден")
    require_org_member(db, user, row.organization_id)
    db.delete(row)
    db.commit()
