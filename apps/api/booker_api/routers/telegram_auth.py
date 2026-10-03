"""Telegram Mini App first factor, with a one-use Booker pending proof."""

import hashlib
import hmac
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.auth_providers.telegram import InvalidTelegramInitData, verify_init_data
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.legal_registry import REQUIRED_KEYS
from booker_api.models import ConsentEvent, PendingExternalAuth, SessionToken, User, UserIdentity
from booker_api.notifications.security import queue_security_notice
from booker_api.rate_limit import auth_limiter, client_key, otp_limiter
from booker_api.routers.legal import current_pack
from booker_api.schemas import AcceptedDocumentIn
from booker_api.security import (
    AuthContext,
    audit,
    auth_context,
    aware,
    ensure_admin_2fa_configured,
    issue_token,
    mark_admin_2fa_verified,
    now,
    verify_password,
)
from booker_api.totp import verify_totp_code

router = APIRouter(tags=["identity"])
PENDING_TTL_MINUTES = 5


class TelegramPrepareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    init_data: str = Field(min_length=1, max_length=8192)


class TelegramCompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending_token: str = Field(min_length=64, max_length=64)
    totp: str | None = Field(default=None, min_length=6, max_length=6)
    accept_offer: StrictBool = False
    accept_privacy: StrictBool = False
    accept_processing: StrictBool = False
    accepted_documents: list[AcceptedDocumentIn] = Field(default_factory=list, max_length=8)
    draft_test_acknowledgement: StrictBool = False


class TelegramIdentityChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)
    totp: str | None = Field(default=None, min_length=6, max_length=6)


class TelegramLinkIn(TelegramIdentityChangeIn):
    pending_token: str = Field(min_length=64, max_length=64)


def _pending_token(proof_hash: str) -> str:
    # Stable for a retry of the same signed initData, without storing a bearer.
    return hmac.new(
        settings.telegram_bot_token.encode(),
        b"booker.telegram.pending.v1\0" + proof_hash.encode(), hashlib.sha256,
    ).hexdigest()


def _token_hash(raw: str) -> str:
    return hashlib.sha256(b"booker.external-pending.v1\0" + raw.encode()).hexdigest()


def _serialize_sqlite(db: Session) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _fresh_account_for_change(
    db: Session, user_id: str, session_key: str, body: TelegramIdentityChangeIn,
) -> User:
    user = db.query(User).filter_by(id=user_id).with_for_update().one_or_none()
    session = db.query(SessionToken).filter_by(token=session_key, user_id=user_id).with_for_update().one_or_none()
    if not user or not session or (session.expires_at and aware(session.expires_at) <= now()):
        raise HTTPException(401, "Сессия недействительна")
    if not user.email or not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Для изменения способов входа подтвердите действующий пароль")
    if user.is_platform_admin or user.is_support_operator:
        ensure_admin_2fa_configured(user)
        otp_limiter.check(f"otp:user:{user.id}")
        if not verify_totp_code(user.totp_secret, body.totp):
            raise HTTPException(403, "Нужен код второго фактора")
    return user


@router.get("/me/identities")
def my_identities(ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)):
    rows = db.query(UserIdentity).filter_by(user_id=ctx.user.id).order_by(UserIdentity.provider).all()
    return {
        "has_password_login": bool(ctx.user.email and ctx.user.password_hash),
        "identities": [
            {"provider": row.provider, "linked_at": row.linked_at,
             "last_login_at": row.last_login_at}
            for row in rows
        ],
    }


@router.post("/me/identities/telegram/link")
def link_telegram(
    body: TelegramLinkIn, request: Request,
    ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "telegram-link"))
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Вход через Telegram не настроен")
    user_id, session_key = ctx.user.id, ctx.session.token
    otp_limiter.check(f"identity-change:user:{user_id}")
    db.rollback()
    _serialize_sqlite(db)
    pending = (db.query(PendingExternalAuth)
               .filter_by(token_hash=_token_hash(body.pending_token), provider="telegram")
               .with_for_update().one_or_none())
    if not pending or pending.consumed_at or aware(pending.expires_at) <= now():
        raise HTTPException(409, "Подтверждение Telegram недействительно")
    linked = (db.query(UserIdentity)
              .filter_by(provider="telegram", provider_subject=pending.provider_subject)
              .with_for_update().one_or_none())
    if linked:
        raise HTTPException(409, "Telegram уже привязан к аккаунту")
    existing = (db.query(UserIdentity)
                .filter_by(user_id=user_id, provider="telegram")
                .with_for_update().one_or_none())
    if existing:
        raise HTTPException(409, "У аккаунта уже есть привязка Telegram")
    user = _fresh_account_for_change(db, user_id, session_key, body)
    db.add(UserIdentity(
        user_id=user.id, provider="telegram", provider_subject=pending.provider_subject,
        link_origin="explicit_link", last_login_at=None,
    ))
    pending.consumed_at = now()
    audit(db, actor_user_id=user.id, action="auth.identity_linked",
          entity_type="user", entity_id=user.id,
          payload={"provider": "telegram", "subject_hash": hashlib.sha256(
              pending.provider_subject.encode()
          ).hexdigest()})
    queue_security_notice(db, recipient=user, template="security.identity_linked",
                          actor_user_id=user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Привязка Telegram уже существует") from exc
    return {"linked": True, "provider": "telegram"}


@router.post("/me/identities/telegram/unlink")
def unlink_telegram(
    body: TelegramIdentityChangeIn, request: Request,
    ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "telegram-unlink"))
    user_id, session_key = ctx.user.id, ctx.session.token
    otp_limiter.check(f"identity-change:user:{user_id}")
    db.rollback()
    _serialize_sqlite(db)
    identity = (db.query(UserIdentity)
                .filter_by(user_id=user_id, provider="telegram")
                .with_for_update().one_or_none())
    if not identity:
        raise HTTPException(404, "Привязка Telegram не найдена")
    user = _fresh_account_for_change(db, user_id, session_key, body)
    # This is the only external provider with a working sign-in flow today.
    # _fresh_account_for_change proved that email + password login remains.
    subject_hash = hashlib.sha256(identity.provider_subject.encode()).hexdigest()
    db.delete(identity)
    db.execute(delete(SessionToken).where(
        SessionToken.user_id == user.id, SessionToken.token != session_key
    ))
    audit(db, actor_user_id=user.id, action="auth.identity_unlinked",
          entity_type="user", entity_id=user.id,
          payload={"provider": "telegram", "subject_hash": subject_hash,
                   "other_sessions_revoked": True})
    queue_security_notice(db, recipient=user, template="security.identity_unlinked",
                          actor_user_id=user.id)
    db.commit()
    return {"unlinked": True, "provider": "telegram"}


@router.post("/auth/telegram/prepare")
def prepare_telegram(body: TelegramPrepareIn, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "telegram-prepare"))
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Вход через Telegram не настроен")
    try:
        claim = verify_init_data(body.init_data, bot_token=settings.telegram_bot_token)
    except InvalidTelegramInitData as exc:
        raise HTTPException(401, "Данные Telegram недействительны") from exc

    token = _pending_token(claim.proof_hash)
    issued_at = now()
    _serialize_sqlite(db)
    # Expired claims cannot pass the HMAC time window again; keep a day's
    # history so an old proof is never accepted twice during clock skew.
    db.execute(delete(PendingExternalAuth).where(
        PendingExternalAuth.expires_at < issued_at - timedelta(days=1)
    ))
    pending = (db.query(PendingExternalAuth)
               .filter_by(provider="telegram", proof_hash=claim.proof_hash)
               .with_for_update().one_or_none())
    if pending is None:
        pending = PendingExternalAuth(
            token_hash=_token_hash(token), provider="telegram",
            provider_subject=claim.subject, proof_hash=claim.proof_hash,
            display_name=f"{claim.first_name} {claim.last_name or ''}".strip()[:255],
            expires_at=issued_at + timedelta(minutes=PENDING_TTL_MINUTES),
        )
        db.add(pending)
    elif pending.consumed_at or aware(pending.expires_at) <= issued_at:
        raise HTTPException(409, "Подтверждение Telegram уже использовано или истекло")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Подтверждение Telegram уже обрабатывается") from exc
    return {"pending_token": token, "expires_at": pending.expires_at}


@router.post("/auth/telegram/complete")
def complete_telegram(body: TelegramCompleteIn, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "telegram-complete"))
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Вход через Telegram не настроен")
    _serialize_sqlite(db)
    pending = (db.query(PendingExternalAuth)
               .filter_by(token_hash=_token_hash(body.pending_token), provider="telegram")
               .with_for_update().one_or_none())
    if not pending or pending.consumed_at or aware(pending.expires_at) <= now():
        raise HTTPException(409, "Подтверждение Telegram недействительно")
    identity = (db.query(UserIdentity)
                .filter_by(provider="telegram", provider_subject=pending.provider_subject)
                .with_for_update().one_or_none())
    issued_at = now()
    if identity:
        user = db.query(User).filter_by(id=identity.user_id).with_for_update().one_or_none()
        if user is None:
            raise HTTPException(409, "Аккаунт недоступен")
        if user.is_platform_admin or user.is_support_operator:
            ensure_admin_2fa_configured(user)
            otp_limiter.check(f"otp:user:{user.id}")
            if not verify_totp_code(user.totp_secret, body.totp):
                raise HTTPException(401, "Нужен код второго фактора")
        identity.last_login_at = issued_at
        is_new = False
    else:
        pack, documents = current_pack(db)
        if not pack["registration_available"]:
            raise HTTPException(503, "Регистрация недоступна до утверждения документов")
        if not (body.accept_offer and body.accept_privacy and body.accept_processing):
            raise HTTPException(422, "Нужны отдельные согласия на документы и обработку")
        if pack["acceptance_effect"] == "test_acknowledgement" and not body.draft_test_acknowledgement:
            raise HTTPException(422, "Нужно явно подтвердить тестовый статус черновика")
        expected = {
            key: {"key": key, "version": documents[key].version,
                  "content_hash": documents[key].content_hash}
            for key in REQUIRED_KEYS
        }
        supplied = {item.key: item.model_dump() for item in body.accepted_documents}
        if len(body.accepted_documents) != len(expected) or supplied != expected:
            raise HTTPException(409, "Версии документов изменились; обновите страницу регистрации")
        user = User(email=None, password_hash=None, full_name=pending.display_name)
        db.add(user)
        db.flush()
        identity = UserIdentity(
            user_id=user.id, provider="telegram", provider_subject=pending.provider_subject,
            link_origin="first_login", last_login_at=issued_at,
        )
        db.add(identity)
        for kind, key in (("offer", "offer"), ("privacy", "privacy"),
                          ("processing", "consent_texts")):
            row = documents[key]
            db.add(ConsentEvent(
                user_id=user.id, kind=kind, document_version_id=row.id,
                document_version=row.version, document_hash=row.content_hash,
                action="accepted", channel="telegram_registration",
                metadata_json=json.dumps({"acceptance_effect": pack["acceptance_effect"]}),
            ))
        audit(db, actor_user_id=user.id, action="user.registered",
              entity_type="user", entity_id=user.id,
              payload={"provider": "telegram", "legal_pack_version": pack["pack_version"],
                       "acceptance_effect": pack["acceptance_effect"]})
        is_new = True
    pending.consumed_at = issued_at
    token = issue_token(db, user)
    if user.is_platform_admin or user.is_support_operator:
        mark_admin_2fa_verified(db, token)
    audit(db, actor_user_id=user.id, action="auth.telegram_login",
          entity_type="user", entity_id=user.id, payload={"new_user": is_new})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Привязка Telegram уже существует") from exc
    return {"token": token, "user_id": user.id, "is_platform_admin": user.is_platform_admin,
            "is_support_operator": user.is_support_operator, "onboarding_required": is_new}
