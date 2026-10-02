import json
import os
from ipaddress import ip_network
from typing import Literal
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

APPROVED_SUPPORT_SLA_SCHEDULE = {
    code: {"timezone": "Europe/Moscow", "weekdays": list(range(7)),
           "start": "10:00", "end": "22:00", "closed_dates": []}
    for code in ("event_day_no_show", "paid_not_confirmed")
}
APPROVED_SUPPORT_SLA_CANONICAL = json.dumps(
    APPROVED_SUPPORT_SLA_SCHEDULE, sort_keys=True, separators=(",", ":")
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOOKER_", extra="ignore")

    runtime_env: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = "sqlite:///./booker.db"
    webhook_secret: str = "dev-webhook-secret"
    # Dev/test only: allow the well-known default webhook secret.
    # Prod must set BOOKER_ALLOW_DEFAULT_WEBHOOK_SECRET=false + BOOKER_WEBHOOK_SECRET.
    allow_default_webhook_secret: bool = True
    payment_provider: str = "stub"
    payment_merchant_id: str = ""
    payment_public_key: str = ""
    payment_secret_key: str = ""
    lawyer_approval_date: str = ""
    legal_publication_approved: bool = False
    payment_flow_approval: str = ""
    support_email: str = "hello@bukergo.ru"
    # Owner-approved daily support window; explicit env setting can override it.
    support_sla_schedule_json: str = json.dumps(APPROVED_SUPPORT_SLA_SCHEDULE, separators=(",", ":"))
    email_from: str = "Букер <noreply@bukergo.ru>"
    email_api_key: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    sms_api_key: str = ""
    object_storage_provider: str = "local"
    object_storage_bucket: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    hold_ttl_hours: int = 24
    pilot_commission_rate: float = 0.10
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://bukergo.ru,https://www.bukergo.ru,"
        "https://bookergo.ru,https://bukergo.online"
    )
    public_url: str = "https://bukergo.ru"
    composition_v2: bool = True
    workspace_switcher: bool = True
    require_admin_2fa_enforced: bool = False
    admin_2fa_step_up_minutes: int = 15
    rate_limit_max_keys: int = 10_000
    rate_limit_backend: Literal["auto", "memory", "database"] = "auto"
    rate_limit_database_url: str = ""
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    ops_public_metrics: bool = False
    ops_alert_transport: Literal["disabled", "test_file"] = "disabled"
    ops_http_5xx_threshold: int = 5
    ops_slow_request_ms: int = 2000
    ops_slow_count_threshold: int = 10
    ops_backup_max_age_hours: int = 30
    ops_restore_max_age_days: int = 30
    ops_outbox_backlog_threshold: int = 50
    ops_outbox_oldest_minutes: int = 60
    ops_outbox_terminal_attempts: int = 3
    ops_reconciliation_max_age_hours: int = 48
    ops_expect_reconciliation: bool = False
    ops_alert_cooldown_minutes: int = 60
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 5_242_880  # 5 MiB
    av_provider: Literal["manual", "clamd"] = "manual"
    av_clamd_socket: str = "/run/clamav/clamd.ctl"
    av_timeout_seconds: float = 5.0
    email_provider: str = "disabled"
    sms_provider: str = "disabled"
    push_provider: str = "disabled"
    in_app_provider: str = "dev"
    password_reset_ttl_hours: int = 2
    organization_invitation_ttl_hours: int = 72


settings = Settings()


def validate_runtime_config(config: Settings = settings) -> None:
    """Reject unsafe production settings before any schema or seed work."""
    if config.runtime_env != "production":
        return

    problems: list[str] = []
    try:
        configured_support_calendar = json.loads(config.support_sla_schedule_json)
    except (TypeError, ValueError):
        configured_support_calendar = None
    if (configured_support_calendar is None or
            json.dumps(configured_support_calendar, sort_keys=True, separators=(",", ":"))
            != APPROVED_SUPPORT_SLA_CANONICAL):
        problems.append("BOOKER_SUPPORT_SLA_SCHEDULE_JSON must match the approved daily Moscow window")
    if config.rate_limit_backend == "memory":
        problems.append("BOOKER_RATE_LIMIT_BACKEND must use the database in production")
    if config.ops_public_metrics:
        problems.append("BOOKER_OPS_PUBLIC_METRICS must remain disabled in production")
    if config.ops_alert_transport != "disabled":
        problems.append("BOOKER_OPS_ALERT_TRANSPORT requires an approved production transport")
    try:
        proxy_networks = [
            ip_network(cidr.strip(), strict=False)
            for cidr in config.trusted_proxy_cidrs.split(",") if cidr.strip()
        ]
        if not proxy_networks or any(network.prefixlen == 0 for network in proxy_networks):
            problems.append("BOOKER_TRUSTED_PROXY_CIDRS must name specific proxy networks")
    except ValueError:
        problems.append("BOOKER_TRUSTED_PROXY_CIDRS contains an invalid network")
    provider = config.payment_provider.strip().lower()
    if provider not in {"external", "disabled"}:
        problems.append("BOOKER_PAYMENT_PROVIDER must be external or disabled")
    secret = config.webhook_secret.strip()
    if (
        config.allow_default_webhook_secret
        or len(secret) < 32
        or len(set(secret)) < 8
        or secret.lower() in {"dev-webhook-secret", "changeme", "placeholder", "test"}
        or secret.lower().startswith(("dev-", "test-", "example-", "placeholder", "{{"))
    ):
        problems.append("BOOKER_WEBHOOK_SECRET must be a non-default secret of at least 32 characters")
    if not config.require_admin_2fa_enforced:
        problems.append("BOOKER_REQUIRE_ADMIN_2FA_ENFORCED must be true")
    if os.environ.get("BOOKER_ALLOW_DEMO_SEED") == "1":
        problems.append("BOOKER_ALLOW_DEMO_SEED must not be enabled")
    if "BOOKER_SESSION_SECRET" in os.environ:
        problems.append("BOOKER_SESSION_SECRET is unsupported; sessions use random database tokens")
    allowed_transports = {
        "email_provider": {"smtp"},
        "sms_provider": {"disabled"},
        "push_provider": {"disabled"},
        "in_app_provider": {"disabled", "audit"},
    }
    for name, allowed in allowed_transports.items():
        if getattr(config, name).strip().lower() not in allowed:
            problems.append(f"BOOKER_{name.upper()} uses an unsupported production transport")
    if config.email_provider.strip().lower() == "smtp" and not config.email_smtp_host.strip():
        problems.append("BOOKER_EMAIL_SMTP_HOST is required for contract-code delivery")

    public = urlsplit(config.public_url.strip())
    if (
        public.scheme != "https"
        or public.hostname != "bukergo.ru"
        or public.port is not None
        or public.username is not None
        or public.password is not None
        or public.path not in {"", "/"}
        or public.query
        or public.fragment
    ):
        problems.append("BOOKER_PUBLIC_URL must be https://bukergo.ru")
    origins = [part.strip() for part in config.cors_origins.split(",")]
    allowed_origins = {"https://bukergo.ru", "https://www.bukergo.ru"}
    if not origins or any(origin not in allowed_origins for origin in origins):
        problems.append("BOOKER_CORS_ORIGINS must contain only approved HTTPS origins")
    if problems:
        raise RuntimeError("unsafe Booker production configuration: " + "; ".join(problems))
