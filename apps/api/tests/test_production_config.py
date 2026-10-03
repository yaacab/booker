"""Production startup must fail before touching the database on unsafe settings."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from booker_api.config import Settings, settings, validate_runtime_config
from booker_api.main import app

ROOT = Path(__file__).resolve().parents[3]
TEST_TOTP_STORAGE_KEY = Fernet.generate_key().decode("ascii")


def production_settings(**overrides) -> Settings:
    values = {
        "runtime_env": "production",
        "payment_provider": "external",
        "webhook_secret": "a9Kq5pL2vX7mR3tY8nB4cD6fG1hJ0sWz",
        "allow_default_webhook_secret": False,
        "require_admin_2fa_enforced": True,
        "totp_encryption_keys": TEST_TOTP_STORAGE_KEY,
        "public_url": "https://bukergo.ru",
        "cors_origins": "https://bukergo.ru,https://www.bukergo.ru",
        "in_app_provider": "audit",
        "email_provider": "smtp",
        "email_smtp_host": "smtp.booker.test",
    }
    return Settings(**{**values, **overrides})


def test_external_production_profile_and_local_defaults(monkeypatch):
    monkeypatch.delenv("BOOKER_ALLOW_DEMO_SEED", raising=False)
    monkeypatch.delenv("BOOKER_SESSION_SECRET", raising=False)
    validate_runtime_config(production_settings())
    validate_runtime_config(Settings(runtime_env="local"))
    validate_runtime_config(Settings(runtime_env="test"))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"payment_provider": "stub"}, "BOOKER_PAYMENT_PROVIDER"),
        ({"payment_provider": "yookassa"}, "BOOKER_PAYMENT_PROVIDER"),
        ({"webhook_secret": "dev-webhook-secret"}, "BOOKER_WEBHOOK_SECRET"),
        ({"webhook_secret": "short"}, "BOOKER_WEBHOOK_SECRET"),
        ({"webhook_secret": "a" * 32}, "BOOKER_WEBHOOK_SECRET"),
        ({"allow_default_webhook_secret": True}, "BOOKER_WEBHOOK_SECRET"),
        ({"require_admin_2fa_enforced": False}, "BOOKER_REQUIRE_ADMIN_2FA_ENFORCED"),
        ({"totp_encryption_keys": ""}, "BOOKER_TOTP_ENCRYPTION_KEYS"),
        ({"totp_encryption_keys": "bad-key"}, "BOOKER_TOTP_ENCRYPTION_KEYS"),
        ({"rate_limit_backend": "memory"}, "BOOKER_RATE_LIMIT_BACKEND"),
        ({"ops_public_metrics": True}, "BOOKER_OPS_PUBLIC_METRICS"),
        ({"ops_alert_transport": "test_file"}, "BOOKER_OPS_ALERT_TRANSPORT"),
        ({"trusted_proxy_cidrs": "0.0.0.0/0"}, "BOOKER_TRUSTED_PROXY_CIDRS"),
        ({"trusted_proxy_cidrs": "bad-cidr"}, "BOOKER_TRUSTED_PROXY_CIDRS"),
        ({"cors_origins": "https://bukergo.ru,http://localhost:3000"}, "BOOKER_CORS_ORIGINS"),
        ({"cors_origins": "*"}, "BOOKER_CORS_ORIGINS"),
        ({"public_url": "http://bukergo.ru"}, "BOOKER_PUBLIC_URL"),
        ({"public_url": "https://evil.example"}, "BOOKER_PUBLIC_URL"),
        ({"in_app_provider": "dev"}, "BOOKER_IN_APP_PROVIDER"),
        ({"email_provider": "dev"}, "BOOKER_EMAIL_PROVIDER"),
        ({"email_provider": "audit"}, "BOOKER_EMAIL_PROVIDER"),
        ({"email_provider": "disabled"}, "BOOKER_EMAIL_PROVIDER"),
        ({"email_smtp_host": ""}, "BOOKER_EMAIL_SMTP_HOST"),
        ({"sms_provider": "audit"}, "BOOKER_SMS_PROVIDER"),
        ({"push_provider": "audit"}, "BOOKER_PUSH_PROVIDER"),
        ({"support_sla_schedule_json": ""}, "BOOKER_SUPPORT_SLA_SCHEDULE_JSON"),
        ({"support_sla_schedule_json": "not-json"}, "BOOKER_SUPPORT_SLA_SCHEDULE_JSON"),
        ({"support_sla_schedule_json": '{"event_day_no_show":{"timezone":"UTC"}}'},
         "BOOKER_SUPPORT_SLA_SCHEDULE_JSON"),
        ({"support_sla_schedule_json": Settings.model_fields["support_sla_schedule_json"].default
          .replace("[0,1,2,3,4,5,6]", "[0,true,2,3,4,5,6]", 1)},
         "BOOKER_SUPPORT_SLA_SCHEDULE_JSON"),
    ],
)
def test_production_profile_rejects_unsafe_values(override, message, monkeypatch):
    monkeypatch.delenv("BOOKER_ALLOW_DEMO_SEED", raising=False)
    monkeypatch.delenv("BOOKER_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match=message):
        validate_runtime_config(production_settings(**override))


def test_production_rejects_demo_seed_and_unsupported_session_secret(monkeypatch):
    monkeypatch.setenv("BOOKER_ALLOW_DEMO_SEED", "1")
    with pytest.raises(RuntimeError, match="BOOKER_ALLOW_DEMO_SEED"):
        validate_runtime_config(production_settings())
    monkeypatch.delenv("BOOKER_ALLOW_DEMO_SEED")
    monkeypatch.setenv("BOOKER_SESSION_SECRET", "a" * 48)
    with pytest.raises(RuntimeError, match="BOOKER_SESSION_SECRET"):
        validate_runtime_config(production_settings())


def test_production_lifespan_rejects_before_schema(monkeypatch):
    import booker_api.main as main_module

    touched = []
    monkeypatch.setattr(settings, "runtime_env", "production")
    monkeypatch.setattr(settings, "payment_provider", "stub")
    monkeypatch.setattr(main_module, "init_schema", lambda engine: touched.append(engine))
    with pytest.raises(RuntimeError, match="BOOKER_PAYMENT_PROVIDER"), TestClient(app):
        pass
    assert touched == []


def test_deploy_preflight_rejects_missing_secret_and_env_override(tmp_path):
    env_file = tmp_path / "booker-api.env"
    unit = ROOT / "infra" / "systemd" / "booker-api.service"
    command = [sys.executable, str(ROOT / "infra" / "preflight_booker_api.py"), str(unit), str(env_file)]
    env_file.write_text(
        "BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n", encoding="utf-8"
    )
    missing = subprocess.run(command, capture_output=True, text=True, check=False)
    assert missing.returncode != 0
    assert "BOOKER_WEBHOOK_SECRET" in missing.stderr
    secret = "a9Kq5pL2vX7mR3tY8nB4cD6fG1hJ0sWz"
    env_file.write_text(
        f"BOOKER_RUNTIME_ENV=local\nBOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n"
        f"BOOKER_WEBHOOK_SECRET={secret}\n"
        f"BOOKER_TOTP_ENCRYPTION_KEYS={TEST_TOTP_STORAGE_KEY}\n"
        "BOOKER_EMAIL_PROVIDER=smtp\nBOOKER_EMAIL_SMTP_HOST=smtp.booker.test\n",
        encoding="utf-8",
    )
    good = subprocess.run(command, capture_output=True, text=True, check=False)
    assert good.returncode == 0, good.stderr
    unsafe_unit = tmp_path / "unsafe-api.service"
    unsafe_unit.write_text(
        unit.read_text(encoding="utf-8").replace(" --no-proxy-headers", ""),
        encoding="utf-8",
    )
    unsafe_proxy = subprocess.run(
        [sys.executable, str(ROOT / "infra" / "preflight_booker_api.py"),
         str(unsafe_unit), str(env_file)],
        capture_output=True, text=True, check=False,
    )
    assert unsafe_proxy.returncode != 0
    assert "direct TCP peer" in unsafe_proxy.stderr
    unsafe_access_unit = tmp_path / "unsafe-access-api.service"
    unsafe_access_unit.write_text(
        unit.read_text(encoding="utf-8").replace(" --no-access-log", ""),
        encoding="utf-8",
    )
    unsafe_access = subprocess.run(
        [sys.executable, str(ROOT / "infra" / "preflight_booker_api.py"),
         str(unsafe_access_unit), str(env_file)],
        capture_output=True, text=True, check=False,
    )
    assert unsafe_access.returncode != 0
    assert "raw request URLs" in unsafe_access.stderr
    env_file.write_text(
        f"BOOKER_RUNTIME_ENV=local\nBOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n"
        f"BOOKER_WEBHOOK_SECRET={secret}\n"
        "BOOKER_PAYMENT_PROVIDER=stub\n",
        encoding="utf-8",
    )
    bypass = subprocess.run(command, capture_output=True, text=True, check=False)
    assert bypass.returncode != 0
    assert "BOOKER_PAYMENT_PROVIDER" in bypass.stderr
    assert secret not in bypass.stderr
    env_file.write_text(f"BOOKER_WEBHOOK_SECRET={secret}\n", encoding="utf-8")
    missing_database = subprocess.run(command, capture_output=True, text=True, check=False)
    assert missing_database.returncode != 0
    assert "BOOKER_DATABASE_URL" in missing_database.stderr
    env_file.write_text(
        f"BOOKER_DATABASE_URL=sqlite:///./booker.db\nBOOKER_WEBHOOK_SECRET={secret}\n",
        encoding="utf-8",
    )
    relative_database = subprocess.run(command, capture_output=True, text=True, check=False)
    assert relative_database.returncode != 0
    assert "production SQLite" in relative_database.stderr
    env_file.write_text(
        "BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n"
        f"export BOOKER_WEBHOOK_SECRET={secret}\n",
        encoding="utf-8",
    )
    unsupported_export = subprocess.run(command, capture_output=True, text=True, check=False)
    assert unsupported_export.returncode != 0
    assert "must not use export" in unsupported_export.stderr
    env_file.write_text(
        "BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n"
        f"export\tBOOKER_WEBHOOK_SECRET={secret}\n",
        encoding="utf-8",
    )
    tab_export = subprocess.run(command, capture_output=True, text=True, check=False)
    assert tab_export.returncode != 0
    assert "must not use export" in tab_export.stderr


def test_demo_seed_cli_rejects_production_before_db(tmp_path):
    database = tmp_path / "demo.db"
    result = subprocess.run(
        [sys.executable, "-m", "booker_api.seed"],
        env={
            **os.environ,
            "BOOKER_RUNTIME_ENV": "production",
            "BOOKER_ALLOW_DEMO_SEED": "1",
            "BOOKER_DATABASE_URL": f"sqlite:///{database}",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "demo seed is forbidden" in result.stderr
    assert not database.exists()


def test_audit_in_app_transport_preserves_log_only_behavior(monkeypatch):
    from booker_api.notifications.registry import AuditTransport, transport_for
    from booker_api.notifications.types import Channel

    monkeypatch.setattr(settings, "in_app_provider", "audit")
    transport = transport_for(Channel.IN_APP)
    assert isinstance(transport, AuditTransport)
    assert transport.provider == "audit"
    monkeypatch.setattr(settings, "email_provider", "audit")
    from booker_api.notifications.registry import NotificationMisconfiguredError

    with pytest.raises(NotificationMisconfiguredError, match="only available for in-app"):
        transport_for(Channel.EMAIL)
