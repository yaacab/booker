"""Runtime checks for OWNER_INPUTS gates (docs/OWNER_INPUTS.md)."""

from __future__ import annotations

from booker_api.config import settings


def _configured(value: str | None) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    return not (v.startswith("{{") and v.endswith("}}"))


def notification_providers() -> dict[str, dict[str, str | bool]]:
    """Current notification transport providers and whether delivery is active."""
    channels = {
        "email": settings.email_provider,
        "sms": settings.sms_provider,
        "push": settings.push_provider,
        "in_app": settings.in_app_provider,
    }
    return {
        channel: {
            "provider": provider,
            "active": provider not in {"", "disabled"},
        }
        for channel, provider in channels.items()
    }


def missing_owner_inputs() -> list[str]:
    """OWNER_INPUT IDs still missing for currently requested capabilities."""
    missing: list[str] = []

    provider = settings.payment_provider.strip().lower()
    if provider not in {"", "stub", "disabled"}:
        if not _configured(settings.payment_merchant_id):
            missing.append("PAYMENT_MERCHANT_ID")
        if not _configured(settings.payment_public_key):
            missing.append("PAYMENT_PUBLIC_KEY")
        if not _configured(settings.payment_secret_key):
            missing.append("PAYMENT_SECRET_KEY")
        if not _configured(settings.webhook_secret) or settings.webhook_secret == "dev-webhook-secret":
            missing.append("PAYMENT_WEBHOOK_SECRET")
        if not _configured(settings.lawyer_approval_date):
            missing.append("LAWYER_APPROVAL_DATE")
        if not _configured(settings.payment_flow_approval):
            missing.append("PAYMENT_FLOW_APPROVAL")

    if settings.email_provider not in {"", "disabled", "dev"} and not _configured(
        settings.email_api_key
    ):
        missing.append("EMAIL_API_KEY")

    if settings.sms_provider not in {"", "disabled", "dev"} and not _configured(
        settings.sms_api_key
    ):
        missing.append("SMS_API_KEY")

    storage = settings.object_storage_provider.strip().lower()
    if storage not in {"", "local", "disabled"}:
        if not _configured(settings.object_storage_bucket):
            missing.append("OBJECT_STORAGE_BUCKET")
        if not _configured(settings.object_storage_access_key):
            missing.append("OBJECT_STORAGE_ACCESS_KEY")
        if not _configured(settings.object_storage_secret_key):
            missing.append("OBJECT_STORAGE_SECRET_KEY")

    return missing
