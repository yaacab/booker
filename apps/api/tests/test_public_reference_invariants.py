"""Public reference endpoints expose only deliberate data and stay stable on repeat reads."""

from booker_api.models import CatalogCategory


def test_health_exposes_flags_without_configuration_values(client, monkeypatch):
    from booker_api.config import settings

    monkeypatch.setattr(settings, "email_api_key", "PRIVATE_EMAIL_API_KEY")
    monkeypatch.setattr(settings, "payment_merchant_id", "PRIVATE_MERCHANT_ID")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "PRIVATE_EMAIL_API_KEY" not in response.text
    assert "PRIVATE_MERCHANT_ID" not in response.text


def test_categories_hide_unpublished_rows_and_repeat_read_is_idempotent(client, SessionLocal):
    with SessionLocal() as db:
        db.add(
            CatalogCategory(
                code="private-reference-test",
                title="PRIVATE_REFERENCE_TITLE",
                group_code="test",
                published=False,
                sort_order=999,
            )
        )
        db.commit()

    first = client.get("/categories")
    assert first.status_code == 200
    assert "PRIVATE_REFERENCE_TITLE" not in first.text
    assert all(set(item) == {"code", "title", "group_code"} for item in first.json()["items"])
    with SessionLocal() as db:
        count_after_first = db.query(CatalogCategory).count()
    second = client.get("/categories")
    assert second.status_code == 200
    assert second.json() == first.json()
    with SessionLocal() as db:
        assert db.query(CatalogCategory).count() == count_after_first


def test_service_templates_contain_only_public_reference_fields(client):
    first = client.get("/service-templates")
    second = client.get("/service-templates")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["items"]
    assert all(
        set(item) == {"id", "category_code", "title", "description"}
        for item in first.json()["items"]
    )
