import hashlib
import json
import re
import secrets
from base64 import b32decode
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.composition import ALLOWED_ORG_KINDS, ALLOWED_ROLES, normalize_kind
from booker_api.config import settings
from booker_api.db import SessionLocal, get_db
from booker_api.legal_registry import REQUIRED_KEYS
from booker_api.models import (
    AuditLog,
    ConsentEvent,
    EmailOutbox,
    EmailVerificationChallenge,
    Organization,
    OrganizationInvitation,
    PasswordResetToken,
    SessionToken,
    StaffRecoveryCode,
    TeamMember,
    User,
    UserNotification,
)
from booker_api.notifications.inbox import notice_payload
from booker_api.notifications.outbox import (
    deliver_outbox_row,
    enqueue_email,
    scrub_password_reset_outbox,
)
from booker_api.notifications.registry import transport_for
from booker_api.notifications.security import queue_security_notice
from booker_api.notifications.service import notify
from booker_api.notifications.transports.dev import dev_inbox_for
from booker_api.notifications.types import Channel, Notification
from booker_api.rate_limit import auth_limiter, client_key, otp_limiter
from booker_api.routers.legal import current_pack
from booker_api.schemas import (
    LoginIn,
    MemberIn,
    OrganizationInvitationAcceptIn,
    OrganizationInvitationIn,
    OrgIn,
    RegisterIn,
)
from booker_api.security import (
    AuthContext,
    audit,
    auth_context,
    aware,
    current_user,
    ensure_admin_2fa_configured,
    hash_password,
    issue_token,
    mark_admin_2fa_verified,
    membership,
    now,
    require_org_member,
    require_support_step_up,
    verify_password,
)
from booker_api.staff_recovery import recovery_code_hash, replace_recovery_codes
from booker_api.totp import verify_totp_code

ADMIN_TOTP_PROOF_TTL_MINUTES = 10
EMAIL_VERIFICATION_TTL_HOURS = 24


@asynccontextmanager
async def identity_lifespan(_app: FastAPI):
    # Clear plaintext links left by older releases before accepting requests.
    with SessionLocal() as db:
        if scrub_password_reset_outbox(db):
            db.commit()
    yield


router = APIRouter(tags=["identity"], lifespan=identity_lifespan)


class AdminTotpChallengeIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class AdminTotpConfirmIn(AdminTotpChallengeIn):
    proof: str = Field(min_length=32, max_length=128)
    secret: str = Field(min_length=32, max_length=32)
    code: str = Field(min_length=6, max_length=6)


class AdminTotpRotateIn(AdminTotpChallengeIn):
    totp: str = Field(min_length=6, max_length=6)
    secret: str = Field(min_length=32, max_length=32)
    code: str = Field(min_length=6, max_length=6)


class AdminTotpRecoverIn(AdminTotpChallengeIn):
    recovery_code: str = Field(min_length=24, max_length=40)
    secret: str = Field(min_length=32, max_length=32)
    code: str = Field(min_length=6, max_length=6)


class AdminRecoveryCodesRegenerateIn(AdminTotpChallengeIn):
    totp: str = Field(min_length=6, max_length=6)


class EmailVerificationRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class EmailVerificationConfirmIn(BaseModel):
    token: str = Field(min_length=32, max_length=128)


def _admin_totp_proof_hash(raw: str) -> str:
    """Domain separation keeps this proof unusable as a password-reset token."""
    return hashlib.sha256(b"booker.admin-totp.v1\0" + raw.encode()).hexdigest()


def _email_verification_hash(raw: str) -> str:
    return hashlib.sha256(b"booker.email-verification.v1\0" + raw.encode()).hexdigest()


def _email_gate_enabled() -> bool:
    # Staging/production must enforce the same policy; local tests enable it explicitly.
    return settings.runtime_env in {"staging", "production"}


def _email_proof_required(user: User) -> bool:
    # Existing memberships continue, but every new grant needs mailbox proof.
    return _email_gate_enabled() and not bool(user.email_verified_at)


def _require_email_proof(user: User) -> None:
    if _email_proof_required(user):
        raise HTTPException(403, "Подтвердите email перед новым доступом к организации")


def _send_email_verification(db: Session, user: User) -> str:
    if not user.email or settings.email_provider != "smtp" or not settings.email_smtp_host.strip():
        return "unavailable"
    issued_at = now()
    raw = secrets.token_urlsafe(32)
    db.execute(
        update(EmailVerificationChallenge)
        .where(
            EmailVerificationChallenge.user_id == user.id,
            EmailVerificationChallenge.consumed_at.is_(None),
            EmailVerificationChallenge.revoked_at.is_(None),
        )
        .values(revoked_at=issued_at)
        .execution_options(synchronize_session=False)
    )
    challenge = EmailVerificationChallenge(
        token_hash=_email_verification_hash(raw),
        user_id=user.id,
        target_email=user.email,
        expires_at=issued_at + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS),
    )
    db.add(challenge)
    audit(db, actor_user_id=user.id, action="auth.email_verification_requested",
          entity_type="user", entity_id=user.id,
          payload={"target_email_hash": hashlib.sha256(user.email.encode()).hexdigest()})
    # Commit the one-use proof before SMTP can expose it to a mailbox.
    db.commit()
    delivery = notify(db, actor_user_id=user.id, notifications=[Notification(
        channel=Channel.EMAIL,
        template="auth.email_verification",
        recipient_user_id=user.id,
        recipient_email=user.email,
        subject="Подтвердите email · Букер",
        body=(f"Подтвердите адрес: {settings.public_url.rstrip('/')}/login#verify={raw}\n"
              f"Ссылка действует {EMAIL_VERIFICATION_TTL_HOURS} часа."),
        entity_type="user", entity_id=user.id,
        metadata={"ephemeral_secret": True, "delivery_id": secrets.token_hex(16)},
    )])
    db.commit()
    return delivery[0]["status"] if delivery else "error"


def _canonical_totp_secret(value: str) -> str:
    if not re.fullmatch(r"[A-Z2-7]{32}", value):
        raise HTTPException(400, "Секрет TOTP должен быть 32 символа Base32")
    decoded = b32decode(value)
    # Reject obvious hand-written patterns; the client must use 20 random bytes.
    if len(decoded) != 20 or len(set(decoded)) < 10:
        raise HTTPException(400, "Секрет TOTP недостаточно случайный")
    return value


def _serialize_auth_change(db: Session) -> None:
    """SQLite ignores FOR UPDATE; reserve its write lock before reading auth state."""
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def issue_invitation_token() -> str:
    return secrets.token_urlsafe(32)


INVITATION_EMAIL_RE = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)


def normalize_invitation_email(value: str) -> str:
    email = value.strip().lower()
    local = email.partition("@")[0]
    if (
        len(email) > 254
        or not INVITATION_EMAIL_RE.fullmatch(email)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise HTTPException(400, "Некорректный email")
    return email


def deliver_invitation_outbox(db: Session, invitation_id: str, actor_user_id: str) -> dict | None:
    row = (
        db.query(EmailOutbox)
        .filter_by(entity_type="organization_invitation", entity_id=invitation_id)
        .one_or_none()
    )
    if not row:
        return None
    return deliver_outbox_row(db, row, actor_user_id=actor_user_id)


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "register"))
    email = normalize_invitation_email(body.email)
    pack, documents = current_pack(db)
    if not pack["registration_available"]:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Регистрация недоступна до утверждения документов")
    if _email_gate_enabled() and (
        settings.email_provider != "smtp" or not settings.email_smtp_host.strip()
    ):
        raise HTTPException(503, "Подтверждение email временно недоступно")
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
    if db.query(User).filter(User.email == email).one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже занят")
    user = User(
        email=email,
        phone=body.phone,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        # Local/test without SMTP cannot complete a mailbox challenge.
        email_verification_required_at=now() if _email_gate_enabled() else None,
        marketing_consent_active=body.marketing_opt_in and pack["acceptance_effect"] == "legal_acceptance",
    )
    db.add(user)
    db.flush()
    for kind, key in (("offer", "offer"), ("privacy", "privacy"), ("processing", "consent_texts")):
        row = documents[key]
        db.add(ConsentEvent(
            user_id=user.id, kind=kind, document_version_id=row.id,
            document_version=row.version, document_hash=row.content_hash,
            action="accepted", channel="registration",
            metadata_json=json.dumps({"acceptance_effect": pack["acceptance_effect"]}),
        ))
    if body.marketing_opt_in:
        row = documents["consent_texts"]
        db.add(ConsentEvent(
            user_id=user.id, kind="marketing_email", document_version_id=row.id,
            document_version=row.version, document_hash=row.content_hash,
            action="accepted", channel="registration",
            metadata_json=json.dumps({"acceptance_effect": pack["acceptance_effect"]}),
        ))
    audit(
        db,
        actor_user_id=user.id,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        payload={
            "legal_pack_version": pack["pack_version"],
            "acceptance_effect": pack["acceptance_effect"],
            "marketing_opt_in": body.marketing_opt_in,
        },
    )
    token = issue_token(db, user)
    db.commit()
    delivery_status = (
        _send_email_verification(db, user) if user.email_verification_required_at
        else "not_required_in_local_test"
    )
    return {
        "token": token, "user_id": user.id, "is_platform_admin": False,
        "email_verified": False,
        "email_verification_required": _email_proof_required(user),
        "email_verification_delivery": delivery_status,
    }


@router.post("/auth/email-verification/request")
def request_email_verification(
    body: EmailVerificationRequestIn, request: Request, db: Session = Depends(get_db)
):
    auth_limiter.check(client_key(request, "email-verification-request"))
    answer = {"ok": True}
    if settings.email_provider != "smtp" or not settings.email_smtp_host.strip():
        if _email_gate_enabled():
            raise HTTPException(503, "Подтверждение email временно недоступно")
        return answer
    try:
        email = normalize_invitation_email(body.email)
    except HTTPException:
        return answer
    otp_limiter.check(f"email-verification:{hashlib.sha256(email.encode()).hexdigest()}")
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == email).with_for_update().one_or_none()
    if user and not user.email_verified_at and verify_password(body.password, user.password_hash):
        _send_email_verification(db, user)
    return answer


@router.post("/auth/email-verification/confirm")
def confirm_email_verification(
    body: EmailVerificationConfirmIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "email-verification-confirm"))
    otp_limiter.check(f"email-verification-confirm:user:{user.id}")
    actor_id = user.id
    # current_user has already opened a read transaction on SQLite.
    db.rollback()
    _serialize_auth_change(db)
    token_hash = _email_verification_hash(body.token.strip())
    current = db.query(User).filter(User.id == actor_id).with_for_update().one()
    challenge = (
        db.query(EmailVerificationChallenge)
        .filter(EmailVerificationChallenge.token_hash == token_hash)
        .with_for_update()
        .one_or_none()
    )
    if not challenge or challenge.user_id != current.id or challenge.target_email != current.email:
        raise HTTPException(409, "Ссылка подтверждения недействительна")
    if challenge.consumed_at and current.email_verified_at:
        return {"email_verified": True, "idempotent": True}
    if challenge.consumed_at or challenge.revoked_at or aware(challenge.expires_at) <= now():
        raise HTTPException(409, "Ссылка подтверждения истекла или заменена")
    verified_at = now()
    challenge.consumed_at = verified_at
    current.email_verified_at = verified_at
    db.execute(
        update(EmailVerificationChallenge)
        .where(EmailVerificationChallenge.user_id == current.id,
               EmailVerificationChallenge.token_hash != token_hash,
               EmailVerificationChallenge.consumed_at.is_(None),
               EmailVerificationChallenge.revoked_at.is_(None))
        .values(revoked_at=verified_at)
        .execution_options(synchronize_session=False)
    )
    audit(db, actor_user_id=current.id, action="auth.email_verified", entity_type="user",
          entity_id=current.id,
          payload={"email_hash": hashlib.sha256(current.email.encode()).hexdigest()})
    db.commit()
    return {"email_verified": True, "idempotent": False}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "login"))
    _serialize_auth_change(db)
    # Serialize issuing a session with password reset for this user.
    user = db.query(User).filter(User.email == body.email.lower()).with_for_update().one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    if user.is_platform_admin or user.is_support_operator:
        ensure_admin_2fa_configured(user)
        otp_limiter.check(f"otp:user:{user.id}")
        if not verify_totp_code(user.totp_secret, body.totp):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужен код второго фактора")
    token = issue_token(db, user)
    if user.is_platform_admin or user.is_support_operator:
        mark_admin_2fa_verified(db, token)
    db.commit()
    return {"token": token, "user_id": user.id,
            "is_platform_admin": user.is_platform_admin,
            "is_support_operator": user.is_support_operator}


@router.post("/auth/admin-totp/challenge")
def admin_totp_challenge(
    body: AdminTotpChallengeIn, request: Request, db: Session = Depends(get_db)
):
    auth_limiter.check(client_key(request, "admin-totp-challenge"))
    answer = {"ok": True}
    if settings.email_provider != "smtp" or not settings.email_smtp_host.strip():
        return answer
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().one_or_none()
    # The operator must verify mailbox ownership before granting admin status;
    # registration alone does not prove control of an email address.
    if not user or not (user.is_platform_admin or user.is_support_operator) or not verify_password(body.password, user.password_hash):
        return answer
    if user.totp_enabled:
        return answer
    otp_limiter.check(f"admin-totp-challenge:user:{user.id}")
    raw = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        token_hash=_admin_totp_proof_hash(raw),
        user_id=user.id,
        expires_at=now() + timedelta(minutes=ADMIN_TOTP_PROOF_TTL_MINUTES),
    ))
    # The proof must be committed before a mailbox can receive it.
    db.commit()
    notify(
        db,
        actor_user_id=user.id,
        notifications=[Notification(
            channel=Channel.EMAIL,
            template="auth.admin_totp_proof",
            recipient_user_id=user.id,
            recipient_email=user.email,
            subject="Подтверждение TOTP · Букер",
            body=(
                "Код подтверждения для настройки второго фактора:\n"
                f"{raw}\n\nДействует {ADMIN_TOTP_PROOF_TTL_MINUTES} минут. "
                "Если вы не запрашивали код, проигнорируйте письмо."
            ),
            entity_type="user",
            entity_id=user.id,
            metadata={"ephemeral_secret": True, "delivery_id": secrets.token_hex(16)},
        )],
    )
    audit(
        db,
        actor_user_id=user.id,
        action="auth.admin_totp_challenge_requested",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    return answer


@router.post("/auth/admin-totp/confirm")
def admin_totp_confirm(
    body: AdminTotpConfirmIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "admin-totp-confirm"))
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().one_or_none()
    if (
        not user
        or not (user.is_platform_admin or user.is_support_operator)
        or user.totp_enabled
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(403, "Подтверждение недействительно")
    otp_limiter.check(f"admin-totp-confirm:user:{user.id}")
    proof_hash = _admin_totp_proof_hash(body.proof.strip())
    proof = db.get(PasswordResetToken, proof_hash)
    if (
        not proof
        or proof.user_id != user.id
        or proof.used_at is not None
        or aware(proof.expires_at) <= now()
    ):
        raise HTTPException(403, "Подтверждение недействительно")
    secret = _canonical_totp_secret(body.secret)
    if not verify_totp_code(secret, body.code):
        raise HTTPException(403, "Подтверждение недействительно")
    consumed = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == proof_hash,
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now(),
        )
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(403, "Подтверждение недействительно")
    user.totp_secret = secret
    user.totp_enabled = True
    recovery_codes = replace_recovery_codes(db, user.id)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    audit(
        db,
        actor_user_id=user.id,
        action="admin.totp_enabled",
        entity_type="user",
        entity_id=user.id,
    )
    queue_security_notice(db, recipient=user, template="security.totp_enabled",
                          actor_user_id=user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"totp_enabled": True, "recovery_codes": recovery_codes}


@router.post("/auth/admin-totp/rotate")
def admin_totp_rotate(
    body: AdminTotpRotateIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "admin-totp-rotate"))
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().one_or_none()
    if (
        not user
        or not (user.is_platform_admin or user.is_support_operator)
        or not user.totp_enabled
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(403, "Подтверждение недействительно")
    otp_limiter.check(f"admin-totp-rotate:user:{user.id}")
    if not verify_totp_code(user.totp_secret, body.totp):
        raise HTTPException(403, "Нужен действующий код текущего второго фактора")
    secret = _canonical_totp_secret(body.secret)
    if secret == user.totp_secret:
        raise HTTPException(400, "Нужен новый секрет второго фактора")
    if not verify_totp_code(secret, body.code):
        raise HTTPException(403, "Неверный код нового второго фактора")
    user.totp_secret = secret
    recovery_codes = replace_recovery_codes(db, user.id)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    audit(
        db,
        actor_user_id=user.id,
        action="admin.totp_rotated",
        entity_type="user",
        entity_id=user.id,
    )
    queue_security_notice(db, recipient=user, template="security.totp_rotated",
                          actor_user_id=user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"totp_enabled": True, "recovery_codes": recovery_codes}


@router.get("/auth/admin-totp/recovery-codes/count")
def staff_recovery_code_count(
    user: User = Depends(require_support_step_up), db: Session = Depends(get_db),
):
    remaining = db.query(StaffRecoveryCode).filter(
        StaffRecoveryCode.user_id == user.id, StaffRecoveryCode.used_at.is_(None),
    ).count()
    return {"remaining": remaining}


@router.post("/auth/admin-totp/recovery-codes/regenerate")
def regenerate_staff_recovery_codes(
    body: AdminRecoveryCodesRegenerateIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "staff-recovery-regenerate"))
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().one_or_none()
    if (
        not user or not (user.is_platform_admin or user.is_support_operator)
        or not user.totp_enabled or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(403, "Подтверждение недействительно")
    otp_limiter.check(f"staff-recovery-regenerate:user:{user.id}")
    if not verify_totp_code(user.totp_secret, body.totp):
        raise HTTPException(403, "Подтверждение недействительно")
    recovery_codes = replace_recovery_codes(db, user.id)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    audit(db, actor_user_id=user.id, action="auth.staff_recovery_codes_regenerated",
          entity_type="user", entity_id=user.id)
    queue_security_notice(db, recipient=user,
                          template="security.recovery_codes_regenerated",
                          actor_user_id=user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"recovery_codes": recovery_codes}


@router.post("/auth/admin-totp/recover")
def recover_staff_totp(
    body: AdminTotpRecoverIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    auth_limiter.check(client_key(request, "staff-totp-recover"))
    _serialize_auth_change(db)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().one_or_none()
    if (
        not user or not (user.is_platform_admin or user.is_support_operator)
        or not user.totp_enabled or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(403, "Подтверждение недействительно")
    # A multi-admin reset needs the separately approved two-person procedure.
    if user.is_platform_admin and db.query(User).filter(User.is_platform_admin.is_(True)).count() != 1:
        raise HTTPException(403, "Восстановление требует проверки двух уполномоченных лиц")
    otp_limiter.check(f"staff-totp-recover:user:{user.id}")
    code_hash = recovery_code_hash(body.recovery_code)
    code_row = db.get(StaffRecoveryCode, code_hash) if code_hash else None
    if not code_row or code_row.user_id != user.id or code_row.used_at is not None:
        raise HTTPException(403, "Подтверждение недействительно")
    secret = _canonical_totp_secret(body.secret)
    if secret == user.totp_secret or not verify_totp_code(secret, body.code):
        raise HTTPException(403, "Подтверждение недействительно")
    code_row.used_at = now()
    db.flush()
    user.totp_secret = secret
    recovery_codes = replace_recovery_codes(db, user.id)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    audit(db, actor_user_id=user.id, action="auth.staff_recovery_code_used",
          entity_type="user", entity_id=user.id)
    audit(db, actor_user_id=user.id, action="auth.staff_totp_recovered",
          entity_type="user", entity_id=user.id)
    queue_security_notice(db, recipient=user, template="security.totp_recovered",
                          actor_user_id=user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"totp_enabled": True, "recovery_codes": recovery_codes}


@router.post("/auth/logout")
def logout(ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)):
    db.delete(ctx.session)
    db.commit()
    return {"ok": True}


@router.post("/auth/recover")
def recover(body: dict, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "recover"))
    email = str(body.get("email") or "").strip().lower()
    # Always same response (no account enumeration).
    ok = {"ok": True, "message": "Если аккаунт существует, инструкция отправлена на почту или во внутренние уведомления."}
    if scrub_password_reset_outbox(db):
        db.commit()
    if not email:
        return ok
    user = db.query(User).filter(User.email == email).one_or_none()
    if not user:
        return ok
    if (user.is_platform_admin or user.is_support_operator) and not user.totp_enabled:
        # No email-only password reset can bootstrap an administrator.
        return ok
    send_email = settings.email_provider == "smtp" and bool(settings.email_smtp_host.strip())
    send_dev_notice = settings.in_app_provider == "dev" and settings.runtime_env in ("local", "test")
    if not (send_email or send_dev_notice):
        return ok
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db.add(
        PasswordResetToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=now() + timedelta(hours=settings.password_reset_ttl_hours),
        )
    )
    reset_url = f"{settings.public_url.rstrip('/')}/login?reset={raw}"
    # A committed token must exist before SMTP can deliver its link. A failed
    # send cannot be retried from a persisted plaintext outbox; request again.
    db.commit()
    notifications = []
    if send_email:
        notifications.append(
            Notification(
                channel=Channel.EMAIL,
                template="auth.password_reset",
                recipient_user_id=user.id,
                recipient_email=user.email,
                subject="Восстановление доступа · Букер",
                body=f"Ссылка для сброса пароля (действует {settings.password_reset_ttl_hours} ч):\n{reset_url}\n\nЕсли вы не запрашивали сброс — проигнорируйте письмо.",
                entity_type="user",
                entity_id=user.id,
                metadata={"ephemeral_secret": True, "delivery_id": secrets.token_hex(16)},
            )
        )
    if send_dev_notice:
        notifications.append(
            Notification(
                channel=Channel.IN_APP,
                template="auth.password_reset",
                recipient_user_id=user.id,
                subject="Сброс пароля",
                body=f"Токен сброса (для демо без SMTP): {raw}",
                entity_type="user",
                entity_id=user.id,
                metadata={"expires_at": (now() + timedelta(hours=settings.password_reset_ttl_hours)).isoformat()},
            )
        )
    notify(
        db,
        actor_user_id=user.id,
        notifications=notifications,
    )
    audit(
        db,
        actor_user_id=user.id,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    return ok


@router.post("/auth/recover/confirm")
def recover_confirm(body: dict, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(client_key(request, "recover-confirm"))
    raw = str(body.get("token") or "").strip()
    password = str(body.get("password") or "")
    if len(password) < 8:
        raise HTTPException(400, "Пароль не короче 8 символов")
    if not raw:
        raise HTTPException(400, "Нужен токен")
    _serialize_auth_change(db)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = db.get(PasswordResetToken, token_hash)
    if not row or row.used_at is not None:
        raise HTTPException(400, "Ссылка недействительна")
    if aware(row.expires_at) <= now():
        raise HTTPException(400, "Ссылка истекла")
    # The same user lock in login prevents a session using the old password
    # from being committed after reset has revoked existing sessions.
    user = db.query(User).filter(User.id == row.user_id).with_for_update().one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.is_platform_admin or user.is_support_operator:
        otp_limiter.check(f"otp:user:{user.id}")
        totp = body.get("totp")
        if (
            not user.totp_enabled
            or not isinstance(totp, str)
            or not verify_totp_code(user.totp_secret, totp)
        ):
            raise HTTPException(403, "Нужен действующий код второго фактора")
    consumed = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now(),
        )
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "Ссылка недействительна")
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now())
        .execution_options(synchronize_session=False)
    )
    user.password_hash = hash_password(password)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    audit(
        db,
        actor_user_id=user.id,
        action="auth.password_reset_completed",
        entity_type="user",
        entity_id=user.id,
    )
    queue_security_notice(db, recipient=user, template="security.password_reset",
                          actor_user_id=user.id)
    db.commit()
    return {"ok": True}


@router.get("/notifications")
def list_notifications(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = 30,
):
    """Return indexed private notices plus bounded legacy/dev compatibility rows."""
    normalized_limit = min(max(limit, 1), 100)
    stored_query = db.query(UserNotification).filter(
        UserNotification.recipient_user_id == user.id
    )
    if not user.is_platform_admin:
        stored_query = stored_query.filter(
            UserNotification.template != "support.first_response_overdue"
        )
    if not user.is_platform_admin and not user.is_support_operator:
        stored_query = stored_query.filter(
            UserNotification.template.notin_(("support.ticket.new", "support.ticket.urgent"))
        )
    stored = (
        stored_query.order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .limit(normalized_limit).all()
    )
    # Older deployments recorded only audit metadata. Narrow the query by the
    # recipient before LIMIT; still verify the parsed JSON before projecting it.
    escaped_id = user.id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(("notification.in_app", "notification.email")),
            AuditLog.payload.like(f"%{escaped_id}%", escape="\\"),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(normalized_limit * 2)
        .all()
    )
    items = [notice_payload(row) for row in stored]
    items.extend(
        dev_inbox_for(user.id, limit=normalized_limit)
        if settings.in_app_provider == "dev"
        else []
    )
    known_keys = {
        (item.get("entity_id"), item.get("template"))
        for item in items
        if item.get("channel") == "in_app"
    }
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except json.JSONDecodeError:
            payload = {}
        if payload.get("recipient_user_id") != user.id:
            continue
        if (
            row.action == "notification.in_app"
            and (row.entity_id, payload.get("template")) in known_keys
        ):
            continue
        items.append(
            {
                "id": row.id,
                "channel": "email" if row.action.endswith("email") else "in_app",
                "template": payload.get("template"),
                "subject": payload.get("subject"),
                "body": payload.get("body"),
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"items": items[:normalized_limit]}


@router.get("/me")
def me(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_booker_org: str | None = Header(default=None, alias="X-Booker-Org"),
):
    members = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    orgs = []
    for m in members:
        org = db.get(Organization, m.organization_id)
        orgs.append(
            {
                "id": m.organization_id,
                "name": org.name if org else "",
                "kind": org.kind if org else "",
                "role": m.role,
                "can_confirm_offer": m.can_confirm_offer,
            }
        )
    active = user.active_organization_id or (orgs[0]["id"] if orgs else None)
    if x_booker_org and (membership(db, user.id, x_booker_org) or user.is_platform_admin):
        active = x_booker_org
    return {
        "id": user.id,
        "email": user.email,
        "email_verified": bool(user.email_verified_at),
        "email_verification_required": _email_proof_required(user),
        "full_name": user.full_name,
        "is_platform_admin": user.is_platform_admin,
        "is_support_operator": user.is_support_operator,
        "totp_enabled": user.totp_enabled,
        "organizations": orgs,
        "active_organization_id": active,
        "workspace_switcher_enabled": settings.workspace_switcher,
    }


@router.post("/orgs")
def create_org(body: OrgIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_email_proof(user)
    kind = normalize_kind(body.kind)
    if kind not in ALLOWED_ORG_KINDS:
        raise HTTPException(400, "kind: customer|artist|venue")
    owned_kinds = []
    for m in db.query(TeamMember).filter(TeamMember.user_id == user.id).all():
        existing = db.get(Organization, m.organization_id)
        if existing:
            owned_kinds.append(existing.kind)
    if kind in owned_kinds and not body.confirm_another_workspace:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Уже есть пространство этого типа. Чтобы создать ещё одно, подтвердите явно.",
        )
    org = Organization(name=body.name, kind=kind, city=body.city)
    db.add(org)
    db.flush()
    db.add(
        TeamMember(
            user_id=user.id,
            organization_id=org.id,
            role="owner",
            can_confirm_offer=True,
        )
    )
    user.active_organization_id = org.id
    audit(
        db,
        actor_user_id=user.id,
        action="org.created",
        entity_type="organization",
        entity_id=org.id,
    )
    db.commit()
    return {"id": org.id, "kind": org.kind, "name": org.name}


@router.get("/orgs/{org_id}")
def get_org(org_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    require_org_member(db, user, org_id)
    members = db.query(TeamMember).filter(TeamMember.organization_id == org_id).all()
    return {
        "id": org.id,
        "name": org.name,
        "kind": org.kind,
        "city": org.city,
        "members": [
            {
                "user_id": m.user_id,
                "role": m.role,
                "can_confirm_offer": m.can_confirm_offer,
            }
            for m in members
        ],
    }


@router.post("/orgs/{org_id}/members")
def add_member(
    org_id: str,
    body: MemberIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_email_proof(user)
    owner = membership(db, user.id, org_id)
    if not owner or owner.role not in {"owner", "admin"}:
        raise HTTPException(403, "Только владелец добавляет команду")
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(400, "role: owner|admin|manager|viewer")
    if body.role == "owner" and owner.role != "owner":
        raise HTTPException(403, "Только владелец может назначить другого владельца")
    target_user = db.get(User, body.user_id)
    if not target_user:
        raise HTTPException(404, "Пользователь не найден")
    if target_user.is_support_operator:
        raise HTTPException(409, "Оператора поддержки нельзя добавить в организацию")
    _require_email_proof(target_user)
    if membership(db, body.user_id, org_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь уже в команде")
    confirm = body.role == "owner" or (body.role != "viewer" and body.can_confirm_offer)
    member = TeamMember(
        user_id=body.user_id,
        organization_id=org_id,
        role=body.role,
        can_confirm_offer=confirm,
    )
    db.add(member)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="org.member_added",
        entity_type="organization",
        entity_id=org_id,
        payload={
            "member_id": member.id,
            "member_user_id": member.user_id,
            "role": member.role,
            "can_confirm_offer": member.can_confirm_offer,
        },
    )
    db.commit()
    return {"id": member.id, "can_confirm_offer": member.can_confirm_offer}


@router.post("/orgs/{org_id}/invitations")
def create_organization_invitation(
    org_id: str,
    body: OrganizationInvitationIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_email_proof(user)
    inviter = membership(db, user.id, org_id)
    if not inviter or inviter.role not in {"owner", "admin"}:
        raise HTTPException(403, "Только владелец или администратор приглашает команду")
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(400, "role: owner|admin|manager|viewer")
    if body.role == "owner" and inviter.role != "owner":
        raise HTTPException(403, "Только владелец может пригласить другого владельца")
    email = normalize_invitation_email(body.email)
    email_transport = transport_for(Channel.EMAIL)
    if email_transport.provider == "disabled":
        raise HTTPException(503, "Отправка email-приглашений не настроена")
    invited_user = db.query(User).filter(User.email == email).one_or_none()
    if invited_user and membership(db, invited_user.id, org_id):
        raise HTTPException(409, "Пользователь уже в команде")
    replay = (
        db.query(OrganizationInvitation)
        .filter_by(
            organization_id=org_id,
            invited_by_user_id=user.id,
            idempotency_key=body.idempotency_key,
        )
        .one_or_none()
    )
    normalized_confirm = body.role == "owner" or (
        body.role != "viewer" and body.can_confirm_offer
    )
    if replay:
        same = (
            replay.invited_by_user_id == user.id
            and replay.organization_id == org_id
            and replay.email == email
            and replay.role == body.role
            and replay.can_confirm_offer == normalized_confirm
        )
        if not same:
            raise HTTPException(409, "Ключ повторного запроса использован с другими данными")
        delivery = (
            deliver_invitation_outbox(db, replay.id, user.id)
            if email_transport.provider == "smtp"
            else None
        )
        return {
            "id": replay.id,
            "status": replay.status,
            "email": replay.email,
            "role": replay.role,
            "expires_at": replay.expires_at.isoformat(),
            "idempotent": True,
            "delivery_status": delivery["status"] if delivery else email_transport.provider,
        }
    pending = (
        db.query(OrganizationInvitation)
        .filter_by(organization_id=org_id, email=email, status="pending")
        .one_or_none()
    )
    if pending:
        if aware(pending.expires_at) > now():
            raise HTTPException(409, "Активное приглашение уже существует")
        pending.status = "expired"
    raw_token = issue_invitation_token()
    invitation = OrganizationInvitation(
        organization_id=org_id,
        email=email,
        invited_user_id=invited_user.id if invited_user else None,
        role=body.role,
        can_confirm_offer=normalized_confirm,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        idempotency_key=body.idempotency_key,
        invited_by_user_id=user.id,
        expires_at=now() + timedelta(hours=settings.organization_invitation_ttl_hours),
    )
    db.add(invitation)
    db.flush()
    accept_url = f"{settings.public_url.rstrip('/')}/invite#token={raw_token}"
    notification = Notification(
        channel=Channel.EMAIL,
        template="organization.invitation",
        recipient_user_id=invited_user.id if invited_user else None,
        recipient_email=email,
        subject="Приглашение в команду · Букер",
        body=(
            "Вас пригласили в команду Букера. "
            f"Ссылка действует {settings.organization_invitation_ttl_hours} ч:\n{accept_url}"
        ),
        entity_type="organization_invitation",
        entity_id=invitation.id,
    )
    if email_transport.provider == "smtp":
        enqueue_email(
            db,
            idempotency_key=f"organization.invitation:{invitation.id}:{email}",
            recipient_email=email,
            subject=notification.subject,
            body=notification.body,
            template=notification.template,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
        )
    audit(
        db,
        actor_user_id=user.id,
        action="org.invitation_created",
        entity_type="organization_invitation",
        entity_id=invitation.id,
        payload={
            "organization_id": org_id,
            "invited_email_hash": hashlib.sha256(email.encode()).hexdigest(),
            "role": invitation.role,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = (
            db.query(OrganizationInvitation)
            .filter_by(
                organization_id=org_id,
                invited_by_user_id=user.id,
                idempotency_key=body.idempotency_key,
            )
            .one_or_none()
        )
        if winner:
            same = (
                winner.email == email
                and winner.role == body.role
                and winner.can_confirm_offer == normalized_confirm
            )
            if not same:
                raise HTTPException(
                    409, "Ключ повторного запроса использован с другими данными"
                ) from None
            delivery = (
                deliver_invitation_outbox(db, winner.id, user.id)
                if email_transport.provider == "smtp"
                else None
            )
            return {
                "id": winner.id,
                "status": winner.status,
                "email": winner.email,
                "role": winner.role,
                "expires_at": winner.expires_at.isoformat(),
                "idempotent": True,
                "delivery_status": delivery["status"] if delivery else email_transport.provider,
            }
        raise HTTPException(409, "Активное приглашение уже существует") from None
    db.refresh(invitation)
    if email_transport.provider == "smtp":
        delivery = deliver_invitation_outbox(db, invitation.id, user.id)
    else:
        delivery_results = notify(
            db,
            actor_user_id=user.id,
            notifications=[notification],
        )
        db.commit()
        delivery = delivery_results[0] if delivery_results else None
    return {
        "id": invitation.id,
        "status": invitation.status,
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
        "idempotent": False,
        "delivery_status": delivery["status"] if delivery else email_transport.provider,
    }


@router.post("/organization-invitations/accept")
def accept_organization_invitation(
    body: OrganizationInvitationAcceptIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(body.token.strip().encode()).hexdigest()
    invitation = (
        db.query(OrganizationInvitation)
        .filter(OrganizationInvitation.token_hash == token_hash)
        .with_for_update()
        .one_or_none()
    )
    if not invitation:
        raise HTTPException(404, "Приглашение не найдено")
    if invitation.status == "accepted" and invitation.invited_user_id == user.id:
        member = membership(db, user.id, invitation.organization_id)
        return {"id": member.id if member else None, "status": "accepted", "idempotent": True}
    if invitation.status != "pending":
        raise HTTPException(409, "Приглашение недействительно")
    if aware(invitation.expires_at) <= now():
        expired = db.execute(
            update(OrganizationInvitation)
            .where(
                OrganizationInvitation.id == invitation.id,
                OrganizationInvitation.status == "pending",
                OrganizationInvitation.expires_at <= now(),
            )
            .values(status="expired")
            .execution_options(synchronize_session=False)
        )
        if expired.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Приглашение уже обработано")
        audit(
            db,
            actor_user_id=user.id,
            action="org.invitation_expired",
            entity_type="organization_invitation",
            entity_id=invitation.id,
            payload={"organization_id": invitation.organization_id},
        )
        db.commit()
        raise HTTPException(410, "Приглашение истекло")
    if not user.email or user.email.lower() != invitation.email:
        raise HTTPException(403, "Приглашение выдано другому пользователю")
    _require_email_proof(user)
    if invitation.invited_user_id and invitation.invited_user_id != user.id:
        raise HTTPException(403, "Приглашение выдано другому пользователю")
    existing = membership(db, user.id, invitation.organization_id)
    claimed = db.execute(
        update(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation.id,
            OrganizationInvitation.status == "pending",
        )
        .values(status="accepted", invited_user_id=user.id, accepted_at=now())
    )
    if claimed.rowcount != 1:
        db.rollback()
        current = db.get(OrganizationInvitation, invitation.id)
        if current and current.status == "accepted" and current.invited_user_id == user.id:
            current_member = membership(db, user.id, current.organization_id)
            return {
                "id": current_member.id if current_member else None,
                "status": "accepted",
                "idempotent": True,
            }
        raise HTTPException(409, "Приглашение недействительно")
    if existing:
        audit(
            db,
            actor_user_id=user.id,
            action="org.invitation_accepted",
            entity_type="organization_invitation",
            entity_id=invitation.id,
            payload={"organization_id": invitation.organization_id, "member_id": existing.id},
        )
        db.commit()
        return {"id": existing.id, "status": "accepted", "idempotent": True}
    member = TeamMember(
        user_id=user.id,
        organization_id=invitation.organization_id,
        role=invitation.role,
        can_confirm_offer=invitation.can_confirm_offer,
    )
    db.add(member)
    db.flush()
    audit(
        db,
        actor_user_id=user.id,
        action="org.invitation_accepted",
        entity_type="organization_invitation",
        entity_id=invitation.id,
        payload={"organization_id": invitation.organization_id, "member_id": member.id},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        current = db.get(OrganizationInvitation, invitation.id)
        current_member = membership(db, user.id, invitation.organization_id)
        if current and current.status == "accepted" and current_member:
            return {"id": current_member.id, "status": "accepted", "idempotent": True}
        raise HTTPException(409, "Приглашение уже обработано") from None
    return {"id": member.id, "status": "accepted", "idempotent": False}


@router.post("/orgs/{org_id}/invitations/{invitation_id}/revoke")
def revoke_organization_invitation(
    org_id: str,
    invitation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    actor = membership(db, user.id, org_id)
    if not actor or actor.role not in {"owner", "admin"}:
        raise HTTPException(403, "Только владелец или администратор отзывает приглашение")
    invitation = db.get(OrganizationInvitation, invitation_id)
    if not invitation or invitation.organization_id != org_id:
        raise HTTPException(404, "Приглашение не найдено")
    if invitation.role == "owner" and actor.role != "owner":
        raise HTTPException(403, "Только владелец отзывает приглашение владельца")
    if invitation.status == "revoked":
        return {"id": invitation.id, "status": "revoked", "idempotent": True}
    if invitation.status != "pending":
        raise HTTPException(409, "Отозвать можно только активное приглашение")
    claimed = db.execute(
        update(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation.id,
            OrganizationInvitation.status == "pending",
        )
        .values(status="revoked", revoked_at=now())
    )
    if claimed.rowcount != 1:
        db.rollback()
        current = db.get(OrganizationInvitation, invitation.id)
        if current and current.status == "revoked":
            return {"id": current.id, "status": "revoked", "idempotent": True}
        raise HTTPException(409, "Отозвать можно только активное приглашение")
    audit(
        db,
        actor_user_id=user.id,
        action="org.invitation_revoked",
        entity_type="organization_invitation",
        entity_id=invitation.id,
        payload={"organization_id": org_id},
    )
    db.commit()
    return {"id": invitation.id, "status": "revoked", "idempotent": False}


@router.post("/me/active-org")
def set_active_org(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org_id = body.get("organization_id")
    if not org_id:
        raise HTTPException(400, "organization_id обязателен")
    require_org_member(db, user, org_id)
    previous = user.active_organization_id
    user.active_organization_id = org_id
    if previous != org_id:
        audit(
            db,
            actor_user_id=user.id,
            action="workspace.switched",
            entity_type="organization",
            entity_id=org_id,
            payload={"from": previous, "to": org_id},
        )
    db.commit()
    return {"active_organization_id": org_id}
