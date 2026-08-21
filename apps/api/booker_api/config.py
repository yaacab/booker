from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOOKER_", extra="ignore")

    database_url: str = "sqlite:///./booker.db"
    webhook_secret: str = "dev-webhook-secret"
    payment_provider: str = "stub"
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


settings = Settings()
