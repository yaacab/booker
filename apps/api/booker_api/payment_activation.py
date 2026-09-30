"""Configuration gate shared by explicitly registered, non-stub payment adapters.

Approval fields record an operator declaration, not automated legal verification.
Registration is code-only; environment variables never import arbitrary modules.
"""
from datetime import date, datetime, timezone

from booker_api.config import settings


def live_configuration_ready(*, commerce: bool = False) -> bool:
    try:
        approved = date.fromisoformat(settings.lawyer_approval_date.strip())
    except ValueError:
        return False
    secret = settings.commerce_webhook_secret if commerce else settings.webhook_secret
    return bool(
        settings.environment.strip().lower() == 'production'
        and (settings.commerce_live_opt_in if commerce else settings.payment_live_opt_in)
        and settings.payment_sandbox_accepted
        and approved <= datetime.now(timezone.utc).date()
        and settings.payment_flow_approval.strip().lower() == 'approved'
        and settings.payment_merchant_id.strip()
        and settings.payment_public_key.strip()
        and settings.payment_secret_key.strip()
        and len(secret.strip()) >= 32
        and secret.strip() != 'dev-webhook-secret'
        and not settings.allow_default_webhook_secret
        and not settings.payment_allow_stub
        and not settings.commerce_allow_stub
        and settings.require_admin_2fa_enforced
    )


def validate_provider_name(name: str) -> None:
    if (not name or name != name.strip().lower() or len(name) > 64
            or not name.replace('-', '').replace('_', '').isalnum()
            or name in {'stub', 'disabled', 'external', 'live'}):
        raise ValueError('Use an explicit, non-reserved provider name')
