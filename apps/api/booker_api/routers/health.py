from fastapi import APIRouter

from booker_api.config import settings
from booker_api.payments.adapter import payment_live_enabled

router = APIRouter()


@router.get("/health")
def health():
    return {
        "ok": True,
        "service": "booker-api",
        "brand": "Букер",
        "flags": {
            "composition_v2": settings.composition_v2,
            "workspace_switcher": settings.workspace_switcher,
            "payment_provider": settings.payment_provider,
            "payment_live_enabled": payment_live_enabled(),
        },
    }
