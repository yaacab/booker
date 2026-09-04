from booker_api.config import settings


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["brand"] == "Букер"
    flags = body["flags"]
    assert flags["composition_v2"] is True
    assert flags["workspace_switcher"] is True
    assert flags["payment_provider"] == "stub"
    assert flags["payment_live_enabled"] is False
    assert flags["notifications"]["email"] == {"provider": "disabled", "active": False}
    assert flags["notifications"]["in_app"] == {"provider": "dev", "active": True}
    assert flags["owner_inputs_missing"] == []


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


def test_health_notification_providers(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    monkeypatch.setattr(settings, "email_api_key", "")

    res = client.get("/health")
    assert res.status_code == 200
    flags = res.json()["flags"]
    assert flags["notifications"]["email"]["provider"] == "sendgrid"
    assert flags["notifications"]["email"]["active"] is True
    assert "EMAIL_API_KEY" in flags["owner_inputs_missing"]
