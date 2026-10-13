"""Read-only legal registry and a user's append-only consent history."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, model_validator
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.data_subject_lock import lock_subject
from booker_api.db import get_db
from booker_api.legal_registry import (
    DOCUMENTS,
    DRAFT_VERSION,
    REQUIRED_KEYS,
    draft_sources_match,
    published_sources_match,
)
from booker_api.models import AuditLog, ConsentEvent, LegalDocumentVersion, User
from booker_api.security import audit, current_user

router = APIRouter(tags=["legal"])


def current_pack(db: Session) -> tuple[dict, dict[str, LegalDocumentVersion]]:
    rows = db.query(LegalDocumentVersion).all()
    published = {row.key: row for row in rows if row.status == "published"}
    drafts = {row.key: row for row in rows if row.status == "draft" and row.version == DRAFT_VERSION}
    published_versions = {row.version for row in published.values()}
    published_ready = (
        all(key in published for key in DOCUMENTS)
        and len(published_versions) == 1
        and not next(iter(published_versions)).endswith("-draft")
        and published_sources_match(published)
    )
    if settings.runtime_env == "production" and not settings.legal_publication_approved:
        published_ready = False
    if published_ready:
        selected = {key: published.get(key) or drafts.get(key) for key in DOCUMENTS}
        status = "published"
        effect = "legal_acceptance"
    elif not published and settings.runtime_env in {"local", "test"} and all(key in drafts for key in REQUIRED_KEYS) and draft_sources_match():
        selected = drafts
        status = "draft"
        effect = "test_acknowledgement"
    else:
        selected = published or drafts
        status = "unavailable"
        effect = "unavailable"
    selected = {key: row for key, row in selected.items() if row is not None}
    versions = {selected[key].version for key in REQUIRED_KEYS if key in selected}
    pack_version = versions.pop() if len(versions) == 1 else None
    return {
        "pack_version": pack_version,
        "status": status,
        "registration_available": status != "unavailable",
        "acceptance_effect": effect,
        "documents": [
            {
                "key": key, "version": row.version, "content_hash": row.content_hash,
                "status": row.status, "required": required, "href": href,
            }
            for key, (_filename, _digest, required, href) in DOCUMENTS.items()
            if (row := selected.get(key)) is not None
        ],
    }, selected


@router.get("/legal/pack")
def legal_pack(db: Session = Depends(get_db)):
    pack, _ = current_pack(db)
    return pack


@router.get("/me/consents")
def my_consents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    events = (
        db.query(ConsentEvent).filter_by(user_id=user.id)
        .order_by(ConsentEvent.created_at, ConsentEvent.id).all()
    )
    latest_marketing = next((event for event in reversed(events) if event.kind == "marketing_email"), None)
    test_selected = bool(
        latest_marketing and latest_marketing.action == "accepted"
        and json.loads(latest_marketing.metadata_json).get("acceptance_effect") == "test_acknowledgement"
    )
    return {
        "marketing_email_active": user.marketing_consent_active,
        "marketing_test_selected": test_selected,
        "legacy_evidence_status": (
            "legacy_unknown" if not events and db.query(AuditLog.id).filter_by(
                actor_user_id=user.id, action="user.registered"
            ).first() is not None else None
        ),
        "history": [
            {
                "id": event.id, "kind": event.kind, "document_version": event.document_version,
                "document_hash": event.document_hash, "action": event.action,
                "channel": event.channel, "created_at": event.created_at,
                "acceptance_effect": json.loads(event.metadata_json).get("acceptance_effect"),
            }
            for event in events
        ],
    }


@router.post("/me/consents/marketing/withdraw")
def withdraw_marketing(user: User = Depends(current_user), db: Session = Depends(get_db)):
    subject = lock_subject(db, user.id)
    if subject is None:
        raise HTTPException(404, "Пользователь не найден")
    previous = (
        db.query(ConsentEvent).filter_by(user_id=user.id, kind="marketing_email")
        .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc()).first()
    )
    if previous is None or previous.action != "accepted":
        db.rollback()
        return {"marketing_email_active": False, "marketing_test_selected": False}
    subject.marketing_consent_active = False
    db.add(ConsentEvent(
        user_id=user.id, kind="marketing_email", document_version_id=previous.document_version_id,
        document_version=previous.document_version, document_hash=previous.document_hash,
        action="withdrawn", channel="account", metadata_json="{}",
    ))
    audit(db, actor_user_id=user.id, action="consent.marketing_withdrawn",
          entity_type="user", entity_id=user.id, payload={"kind": "marketing_email"})
    db.commit()
    return {"marketing_email_active": False, "marketing_test_selected": False}


class ReacceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted_documents: list[dict[str, str]]
    accept_offer: StrictBool = False
    accept_privacy: StrictBool = False
    accept_processing: StrictBool = False

    @model_validator(mode="after")
    def require_explicit_confirmation(self):
        if not (self.accept_offer and self.accept_privacy and self.accept_processing):
            raise ValueError("Нужны отдельные подтверждения всех обязательных документов")
        return self


@router.post("/me/consents/reaccept")
def reaccept_current(body: ReacceptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    pack, selected = current_pack(db)
    if pack["status"] != "published":
        raise HTTPException(409, "Нет опубликованной редакции для повторного принятия")
    expected = {key: {"key": key, "version": selected[key].version,
                      "content_hash": selected[key].content_hash} for key in REQUIRED_KEYS}
    supplied = {item.get("key"): item for item in body.accepted_documents}
    if len(body.accepted_documents) != len(expected) or supplied != expected:
        raise HTTPException(409, "Нужно принять текущие версии документов")
    subject = lock_subject(db, user.id)
    if subject is None:
        raise HTTPException(404, "Пользователь не найден")
    latest = {
        kind: db.query(ConsentEvent).filter_by(user_id=user.id, kind=kind, action="accepted")
        .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc()).first()
        for kind in ("offer", "privacy", "processing")
    }
    if all(latest[kind] and latest[kind].document_version_id == selected[key].id
           and json.loads(latest[kind].metadata_json).get("acceptance_effect") == "legal_acceptance"
           for kind, key in (("offer", "offer"), ("privacy", "privacy"), ("processing", "consent_texts"))):
        raise HTTPException(409, "Текущая редакция уже принята")
    for kind, key in (("offer", "offer"), ("privacy", "privacy"), ("processing", "consent_texts")):
        row = selected[key]
        db.add(ConsentEvent(user_id=user.id, kind=kind, document_version_id=row.id,
                            document_version=row.version, document_hash=row.content_hash,
                            action="accepted", channel="account",
                            metadata_json='{"acceptance_effect":"legal_acceptance"}'))
    audit(db, actor_user_id=user.id, action="consent.reaccepted", entity_type="user",
          entity_id=user.id, payload={"version": pack["pack_version"]})
    db.commit()
    return {"accepted": True, "pack_version": pack["pack_version"]}
