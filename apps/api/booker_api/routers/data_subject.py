"""Bounded data-subject workflow; no destructive or export executor is enabled."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.data_subject_lock import lock_subject
from booker_api.db import get_db
from booker_api.models import (
    AuditLog,
    ConsentEvent,
    DataSubjectRequest,
    DataSubjectRequestEvent,
    LegalHold,
    SavedSearch,
    SessionToken,
    SupportTicket,
    TeamMember,
    User,
)
from booker_api.security import audit, current_user, require_admin_step_up

router = APIRouter(tags=["data-subject"])

RequestType = Literal["access", "export", "restrict", "delete", "correct"]
RequestStatus = Literal["pending", "in_review", "needs_info", "approved", "rejected", "completed", "cancelled"]
ReasonCode = Literal["review_started", "more_information", "scope_accepted", "scope_rejected", "policy_pending"]
HoldReason = Literal["dispute", "security_incident", "financial_review", "other_review"]
CorrectionField = Literal["email", "phone", "full_name"]

ADMIN_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_review", "needs_info", "rejected"},
    "in_review": {"needs_info", "approved", "rejected"},
    "needs_info": {"in_review", "rejected"},
    "approved": {"completed"},
}
ADMIN_REASONS: dict[str, set[str]] = {
    "in_review": {"review_started"},
    "needs_info": {"more_information"},
    "approved": {"scope_accepted"},
    "rejected": {"scope_rejected", "policy_pending"},
    "completed": {"scope_accepted"},
}


class SubjectRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: RequestType
    correction_field: CorrectionField | None = None

    @model_validator(mode="after")
    def correction_only_for_correction(self):
        if (self.request_type == "correct") != (self.correction_field is not None):
            raise ValueError("Поле исправления нужно только для запроса correct")
        return self


class SubjectTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RequestStatus
    decision_reason_code: ReasonCode


class LegalHoldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_user_id: str
    scope: Literal["user"] = "user"
    reason_code: HoldReason


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _request_payload(row: DataSubjectRequest) -> dict:
    return {
        "id": row.id,
        "subject_user_id": row.subject_user_id,
        "request_type": row.request_type,
        "correction_field": row.correction_field,
        "status": row.status,
        "state_version": row.state_version,
        "decision_reason_code": row.decision_reason_code,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _detail(db: Session, row: DataSubjectRequest) -> dict:
    result = _request_payload(row)
    events = db.query(DataSubjectRequestEvent).filter_by(request_id=row.id).order_by(
        DataSubjectRequestEvent.state_version.asc()
    ).all()
    result["events"] = [
        {"from_status": event.from_status, "to_status": event.to_status,
         "reason_code": event.reason_code, "state_version": event.state_version,
         "created_at": event.created_at.isoformat()}
        for event in events
    ]
    return result


def _own(db: Session, user: User, request_id: str) -> DataSubjectRequest:
    row = db.get(DataSubjectRequest, request_id)
    if row is None or row.subject_user_id != user.id:
        raise HTTPException(404, "Запрос не найден")
    return row


def _admin_row(db: Session, request_id: str) -> DataSubjectRequest:
    row = db.get(DataSubjectRequest, request_id)
    if row is None:
        raise HTTPException(404, "Запрос не найден")
    return row


def _active_hold(db: Session, user_id: str) -> bool:
    return db.query(LegalHold.id).filter(
        LegalHold.subject_user_id == user_id, LegalHold.released_at.is_(None)
    ).first() is not None


def _transition(
    db: Session, row: DataSubjectRequest, actor: User, target: str,
    reason: str | None, expected_version: int,
) -> dict:
    if row.state_version != expected_version:
        raise HTTPException(409, "Запрос изменился")
    previous = row.status
    at = _utcnow()
    changed = db.execute(
        update(DataSubjectRequest).where(
            DataSubjectRequest.id == row.id,
            DataSubjectRequest.status == previous,
            DataSubjectRequest.state_version == expected_version,
        ).values(
            status=target,
            state_version=DataSubjectRequest.state_version + 1,
            updated_at=at,
            decided_by_user_id=actor.id if target in {"approved", "rejected", "completed"} else row.decided_by_user_id,
            decision_reason_code=reason if target in {"approved", "rejected", "completed"} else row.decision_reason_code,
        ).execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Запрос изменился")
    db.add(DataSubjectRequestEvent(
        request_id=row.id, actor_user_id=actor.id, from_status=previous,
        to_status=target, reason_code=reason, state_version=expected_version + 1,
        created_at=at,
    ))
    audit(db, actor_user_id=actor.id, action="data_subject.request.transitioned",
          entity_type="data_subject_request", entity_id=row.id,
          payload={"from": previous, "to": target, "reason_code": reason})
    db.commit()
    db.refresh(row)
    return _detail(db, row)


@router.post("/data-subject/requests", status_code=status.HTTP_201_CREATED)
def create_request(
    body: SubjectRequestIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    existing = db.query(DataSubjectRequest).filter_by(
        subject_user_id=user.id, idempotency_key_hash=key_hash
    ).one_or_none()
    if existing:
        if existing.request_type != body.request_type or existing.correction_field != body.correction_field:
            raise HTTPException(409, "Idempotency-Key уже использован")
        return _detail(db, existing)
    at = _utcnow()
    row = DataSubjectRequest(
        subject_user_id=user.id, request_type=body.request_type,
        correction_field=body.correction_field, idempotency_key_hash=key_hash,
        status="pending", state_version=0, created_at=at, updated_at=at,
    )
    try:
        db.add(row)
        db.flush()
        db.add(DataSubjectRequestEvent(
            request_id=row.id, actor_user_id=user.id, from_status=None,
            to_status="pending", state_version=0, created_at=at,
        ))
        audit(db, actor_user_id=user.id, action="data_subject.request.created",
              entity_type="data_subject_request", entity_id=row.id,
              payload={"request_type": body.request_type})
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.query(DataSubjectRequest).filter_by(
            subject_user_id=user.id, idempotency_key_hash=key_hash
        ).one_or_none()
        if replay and replay.request_type == body.request_type and replay.correction_field == body.correction_field:
            return _detail(db, replay)
        raise HTTPException(409, "Idempotency-Key уже использован") from None
    db.refresh(row)
    return _detail(db, row)


@router.get("/data-subject/requests")
def list_own_requests(
    limit: int = 20, offset: int = 0,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if limit < 1 or limit > 50 or offset < 0 or offset > 10000:
        raise HTTPException(422, "Неверная страница")
    query = db.query(DataSubjectRequest).filter_by(subject_user_id=user.id)
    total = query.count()
    rows = query.order_by(
        DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc()
    ).offset(offset).limit(limit).all()
    return {"items": [_request_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/data-subject/requests/{request_id}")
def get_own_request(request_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _detail(db, _own(db, user, request_id))


@router.post("/data-subject/requests/{request_id}/cancel")
def cancel_own_request(
    request_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _own(db, user, request_id)
    if row.status not in {"pending", "needs_info"}:
        raise HTTPException(409, "Отмена в этом статусе недоступна")
    return _transition(db, row, user, "cancelled", None, expected_version)


@router.get("/data-subject/requests/{request_id}/export-manifest")
def own_export_manifest(request_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _own(db, user, request_id)
    if row.request_type not in {"access", "export"}:
        raise HTTPException(404, "Манифест не найден")
    return {"request_id": row.id, "generator_enabled": False, "ready": False,
            "download_url": None, "scope": ["account", "memberships", "owned_activity"],
            "status": row.status}


@router.get("/admin/data-subject/requests")
def admin_list_requests(
    request_status: RequestStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
):
    del admin
    if limit < 1 or limit > 50 or offset < 0 or offset > 10000:
        raise HTTPException(422, "Неверная страница")
    query = db.query(DataSubjectRequest)
    if request_status:
        query = query.filter(DataSubjectRequest.status == request_status)
    total = query.count()
    rows = query.order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc()).offset(offset).limit(limit).all()
    return {"items": [_request_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/admin/data-subject/requests/{request_id}")
def admin_get_request(
    request_id: str, admin: User = Depends(require_admin_step_up), db: Session = Depends(get_db),
):
    del admin
    row = _admin_row(db, request_id)
    return {**_detail(db, row), "active_hold": _active_hold(db, row.subject_user_id)}


@router.post("/admin/data-subject/requests/{request_id}/transition")
def admin_transition_request(
    request_id: str,
    body: SubjectTransitionIn,
    admin: User = Depends(require_admin_step_up),
    db: Session = Depends(get_db),
    expected_version: int = Header(alias="If-Match", ge=0),
):
    row = _admin_row(db, request_id)
    if body.status not in ADMIN_TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, "Переход статуса недоступен")
    if body.decision_reason_code not in ADMIN_REASONS.get(body.status, set()):
        raise HTTPException(422, "Код причины не соответствует статусу")
    if body.status in {"approved", "rejected", "completed"} and admin.id == row.subject_user_id:
        raise HTTPException(403, "Нельзя принять решение по своему запросу")
    if body.status == "completed" and row.request_type != "restrict":
        raise HTTPException(409, "Исполнительный механизм для этого типа не включён")
    if (row.request_type == "delete" and body.status == "approved") or (row.request_type == "restrict" and body.status == "approved"):
        subject = lock_subject(db, row.subject_user_id)
        if subject is None:
            raise HTTPException(409, "Субъект не найден")
        db.refresh(row)
    if row.request_type == "delete" and body.status in {"approved", "completed"} and _active_hold(db, row.subject_user_id):
        raise HTTPException(409, "Действует legal hold")
    if row.request_type == "restrict" and body.status == "approved":
        subject.optional_processing_restricted = True
        previous = (
            db.query(ConsentEvent).filter_by(user_id=subject.id, kind="marketing_email")
            .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc()).first()
        )
        if previous is not None and previous.action == "accepted":
            db.add(ConsentEvent(
                user_id=subject.id, kind="marketing_email", document_version_id=previous.document_version_id,
                document_version=previous.document_version, document_hash=previous.document_hash,
                action="withdrawn", channel="data_subject", metadata_json="{}",
            ))
        subject.marketing_consent_active = False
        db.execute(update(SavedSearch).where(SavedSearch.user_id == subject.id).values(notify_consent=False))
    return _transition(db, row, admin, body.status, body.decision_reason_code, expected_version)


@router.get("/admin/data-subject/requests/{request_id}/deletion-plan")
def admin_deletion_plan(
    request_id: str, admin: User = Depends(require_admin_step_up), db: Session = Depends(get_db),
):
    del admin
    row = _admin_row(db, request_id)
    if row.request_type != "delete":
        raise HTTPException(404, "План не найден")
    subject = row.subject_user_id
    def count(model, column):
        return int(db.query(func.count()).select_from(model).filter(column == subject).scalar() or 0)
    active_hold = _active_hold(db, subject)
    return {
        "request_id": row.id, "dry_run": True, "executor_enabled": False,
        "blocked": True, "block_reasons": ["active_legal_hold"] if active_hold else ["retention_policy_unapproved"],
        "categories": [
            {"code": "account", "count": 1, "action": "review"},
            {"code": "sessions", "count": count(SessionToken, SessionToken.user_id), "action": "review"},
            {"code": "memberships", "count": count(TeamMember, TeamMember.user_id), "action": "review"},
            {"code": "saved_searches", "count": count(SavedSearch, SavedSearch.user_id), "action": "review"},
            {"code": "support_tickets", "count": count(SupportTicket, SupportTicket.author_user_id), "action": "review"},
            {"code": "audit_events", "count": count(AuditLog, AuditLog.actor_user_id), "action": "retain_review"},
            {"code": "financial_and_contractual", "count": None, "action": "retain_review"},
        ],
    }


def _hold_payload(row: LegalHold) -> dict:
    return {"id": row.id, "subject_user_id": row.subject_user_id, "scope": row.scope,
            "reason_code": row.reason_code, "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at.isoformat(), "released_by_user_id": row.released_by_user_id,
            "released_at": row.released_at.isoformat() if row.released_at else None}


def _suspend_approved_deletions(db: Session, subject_user_id: str, actor_user_id: str) -> None:
    """A new hold supersedes earlier approval before either becomes visible."""
    rows = db.query(DataSubjectRequest).filter_by(
        subject_user_id=subject_user_id, request_type="delete", status="approved"
    ).all()
    for request in rows:
        old_version = request.state_version
        changed = db.execute(update(DataSubjectRequest).where(
            DataSubjectRequest.id == request.id,
            DataSubjectRequest.status == "approved",
            DataSubjectRequest.state_version == old_version,
        ).values(status="in_review", state_version=old_version + 1,
                 updated_at=_utcnow()).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Запрос изменился")
        db.add(DataSubjectRequestEvent(
            request_id=request.id, actor_user_id=actor_user_id,
            from_status="approved", to_status="in_review",
            reason_code="policy_pending", state_version=old_version + 1,
            created_at=_utcnow(),
        ))
        audit(db, actor_user_id=actor_user_id, action="data_subject.request.transitioned",
              entity_type="data_subject_request", entity_id=request.id,
              payload={"from": "approved", "to": "in_review", "reason_code": "policy_pending"})


@router.get("/admin/legal-holds")
def admin_list_holds(
    subject_user_id: str,
    admin: User = Depends(require_admin_step_up), db: Session = Depends(get_db),
):
    del admin
    rows = db.query(LegalHold).filter_by(subject_user_id=subject_user_id).order_by(LegalHold.created_at.desc()).limit(100).all()
    return {"items": [_hold_payload(row) for row in rows]}


@router.post("/admin/legal-holds", status_code=status.HTTP_201_CREATED)
def admin_create_hold(
    body: LegalHoldIn, admin: User = Depends(require_admin_step_up), db: Session = Depends(get_db),
):
    if lock_subject(db, body.subject_user_id) is None:
        raise HTTPException(404, "Субъект не найден")
    if _active_hold(db, body.subject_user_id):
        raise HTTPException(409, "Legal hold уже действует")
    row = LegalHold(subject_user_id=body.subject_user_id, scope=body.scope,
                    reason_code=body.reason_code, created_by_user_id=admin.id, created_at=_utcnow())
    try:
        db.add(row)
        db.flush()
        _suspend_approved_deletions(db, body.subject_user_id, admin.id)
        audit(db, actor_user_id=admin.id, action="data_subject.hold.created",
              entity_type="legal_hold", entity_id=row.id, payload={"reason_code": row.reason_code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Legal hold уже действует") from None
    db.refresh(row)
    return _hold_payload(row)


@router.post("/admin/legal-holds/{hold_id}/release")
def admin_release_hold(
    hold_id: str, admin: User = Depends(require_admin_step_up), db: Session = Depends(get_db),
):
    row = db.get(LegalHold, hold_id)
    if row is None:
        raise HTTPException(404, "Legal hold не найден")
    if lock_subject(db, row.subject_user_id) is None:
        raise HTTPException(409, "Субъект не найден")
    db.refresh(row)
    if row.released_at is not None:
        raise HTTPException(409, "Legal hold уже снят")
    changed = db.execute(update(LegalHold).where(
        LegalHold.id == hold_id, LegalHold.released_at.is_(None)
    ).values(released_at=_utcnow(), released_by_user_id=admin.id))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Legal hold уже изменился")
    audit(db, actor_user_id=admin.id, action="data_subject.hold.released",
          entity_type="legal_hold", entity_id=row.id, payload={})
    db.commit()
    db.refresh(row)
    return _hold_payload(row)
