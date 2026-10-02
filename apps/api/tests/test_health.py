from booker_api.config import settings


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body == {"ok": True}
    assert res.headers["cache-control"] == "no-store"


def test_readiness_ok_in_dev(client):
    res = client.get("/readiness")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["checks"]["database"] is True
    assert body["flags"]["payment_live_enabled"] is False
    assert body["flags"]["owner_inputs_missing"] == []


def test_readiness_reports_missing_owner_inputs_for_live_payment(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "payment_merchant_id", "")

    res = client.get("/readiness")
    assert res.status_code == 503
    body = res.json()
    assert body["ready"] is False
    missing = body["flags"]["owner_inputs_missing"]
    assert "PAYMENT_MERCHANT_ID" in missing
    assert "PAYMENT_PUBLIC_KEY" in missing
    assert "LAWYER_APPROVAL_DATE" in missing


def test_readiness_notification_providers(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    monkeypatch.setattr(settings, "email_api_key", "")

    res = client.get("/readiness")
    assert res.status_code == 503
    flags = res.json()["flags"]
    assert flags["notifications"]["email"]["provider"] == "sendgrid"
    assert flags["notifications"]["email"]["active"] is True
    assert "EMAIL_API_KEY" in flags["owner_inputs_missing"]


def test_production_readiness_requires_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "runtime_env", "production")
    res = client.get("/readiness")
    assert res.status_code == 401
    assert "flags" not in res.text


def test_production_readiness_rejects_member_and_allows_admin(client, monkeypatch):
    from cryptography.fernet import Fernet

    from tests.conftest import auth_header, register
    from tests.test_admin import _promote_admin
    from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers

    # Use one explicit key across enrollment and production-mode reads.
    monkeypatch.setattr(settings, "totp_encryption_keys", Fernet.generate_key().decode("ascii"))
    member = register(client, "perimeter-member@booker.test", "Member")
    admin = _promote_admin(client, "perimeter-admin@booker.test", totp=TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "runtime_env", "production")
    monkeypatch.setattr("booker_api.security.otp_limiter.check", lambda _key: None)
    assert client.get("/readiness", headers=auth_header(member["token"])).status_code == 403
    assert client.get("/readiness", headers=auth_header(admin["pre_promotion_token"])).status_code == 403
    answer = client.get("/readiness", headers=admin_totp_headers(admin["token"]))
    assert answer.status_code == 200
    assert "detail" not in answer.json(), answer.json()
    assert answer.json()["checks"]["database"] is True


def test_internal_readiness_only_returns_database_state(client, monkeypatch):
    import booker_api.routers.health as health_module

    assert client.get("/internal/readiness").json() == {"ready": True}
    monkeypatch.setattr(health_module, "_database_ready", lambda: False)
    response = client.get("/internal/readiness")
    assert response.status_code == 503
    assert response.json() == {"ready": False}
    assert response.headers["cache-control"] == "no-store"


def test_production_internal_probe_rejects_proxied_request(client, monkeypatch):
    monkeypatch.setattr(settings, "runtime_env", "production")
    response = client.get("/internal/readiness", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 404
    assert "ready" not in response.text
