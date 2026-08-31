from fastapi import APIRouter

from booker_api.config import settings

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
        },
    }
