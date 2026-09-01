from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from booker_api.config import settings
from booker_api.db import engine
from booker_api.owner_inputs import missing_owner_inputs, notification_providers
from booker_api.payments.adapter import payment_live_enabled

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
    return {
        "ok": True,
        "service": "booker-api",
        "brand": "Букер",
        "flags": _feature_flags(),
    }


@router.get("/readiness")
def readiness():
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
    return JSONResponse(body, status_code=200 if ready else 503)
