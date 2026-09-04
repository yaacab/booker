from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOOKER_", extra="ignore")

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
    payment_flow_approval: str = ""
    support_email: str = ""
    email_api_key: str = ""
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
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 5_242_880  # 5 MiB
    email_provider: str = "disabled"
    sms_provider: str = "disabled"
    push_provider: str = "disabled"
    in_app_provider: str = "dev"


settings = Settings()
