from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.db import engine, get_db
from booker_api.owner_inputs import missing_owner_inputs, notification_providers
from booker_api.payments.adapter import payment_live_enabled
from booker_api.security import authenticate_token, bearer, ensure_admin_2fa_session

router = APIRouter()


def _feature_flags() -> dict:
    return {
        "composition_v2": settings.composition_v2,
        "workspace_switcher": settings.workspace_switcher,
        "payment_provider": settings.payment_provider,
        "payment_live_enabled": payment_live_enabled(),
        "notifications": notification_providers(),
        "owner_inputs_missing": missing_owner_inputs(),
    }


def _database_ready() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


@router.get("/health")
def health():
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


@router.get("/internal/readiness", include_in_schema=False)
def internal_readiness(request: Request):
    """DB probe for the loopback-only API service; nginx denies its public path."""
    if settings.runtime_env == "production" and (
        request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or request.headers.get("x-forwarded-proto") is not None
    ):
        raise HTTPException(404, "Not found")
    ready = _database_ready()
    return JSONResponse(
        {"ready": ready}, status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/readiness")
def readiness(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if settings.runtime_env == "production":
        if credentials is None:
            raise HTTPException(401, "Нужна авторизация")
        user, session = authenticate_token(db, credentials.credentials)
        if not user.is_platform_admin:
            raise HTTPException(403, "Только администратор")
        ensure_admin_2fa_session(request, db, user, session, force=True)
    db_ok = _database_ready()
    missing = missing_owner_inputs()
    ready = db_ok and not missing
    body = {
        "ready": ready,
        "service": "booker-api",
        "checks": {
            "database": db_ok,
        },
        "flags": _feature_flags(),
    }
    return JSONResponse(body, status_code=200 if ready else 503, headers={"Cache-Control": "no-store"})
