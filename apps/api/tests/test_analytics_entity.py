from tests.conftest import auth_header, register


def test_client_event_uses_unique_entity_id(client):
    user = register(client, "analytics-entity@booker.test", "Analytics")
    res = client.post(
        "/analytics/events",
        json={"name": "search.performed", "properties": {"city": "Москва"}},
        headers=auth_header(user["token"]),
    )
    assert res.status_code == 200
    db = client.app.state.SessionLocal()
    try:
        from booker_api.models import AuditLog

        rows = db.query(AuditLog).filter(AuditLog.action == "client.event").all()
        assert len(rows) == 1
        assert rows[0].entity_id != "search.performed"
        assert rows[0].actor_user_id == user["user_id"]
    finally:
        db.close()
