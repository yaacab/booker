import pytest

from booker_api.config import settings
from booker_api.models import AuditLog, ConsentEvent, LegalDocumentVersion, User, utcnow
from tests.conftest import auth_header, register


def _accepted(pack):
    return [
        {k: doc[k] for k in ("key", "version", "content_hash")}
        for doc in pack["documents"] if doc["required"]
    ]


def _reaccept(pack):
    return {"accepted_documents": _accepted(pack), "accept_offer": True,
            "accept_privacy": True, "accept_processing": True}


def test_draft_pack_is_explicit_and_registration_records_exact_documents(client, SessionLocal):
    pack = client.get("/legal/pack").json()
    assert pack["status"] == "draft"
    assert pack["pack_version"] == "2026-10-01-draft"
    assert pack["acceptance_effect"] == "test_acknowledgement"
    assert {d["key"] for d in pack["documents"] if d["required"]} == {
        "offer", "privacy", "consent_texts",
    }
    base = {"email": "exact-legal@booker.test", "password": "password1", "full_name": "Legal",
            "accept_offer": True, "accept_privacy": True, "accept_processing": True,
            "marketing_opt_in": True,
            "accepted_documents": _accepted(pack), "draft_test_acknowledgement": True}
    assert client.post("/auth/register", json={**base, "draft_test_acknowledgement": False}).status_code == 422
    stale = [dict(item) for item in base["accepted_documents"]]
    stale[0]["content_hash"] = "0" * 64
    assert client.post("/auth/register", json={**base, "accepted_documents": stale}).status_code == 409
    result = client.post("/auth/register", json=base)
    assert result.status_code == 200, result.text
    user_id = result.json()["user_id"]
    recorded = client.get("/me/consents", headers=auth_header(result.json()["token"])).json()
    assert {event["acceptance_effect"] for event in recorded["history"]} == {"test_acknowledgement"}
    with SessionLocal() as db:
        events = db.query(ConsentEvent).filter_by(user_id=user_id).all()
        assert {event.kind for event in events} == {"offer", "privacy", "processing", "marketing_email"}
        assert all(event.action == "accepted" and event.document_hash for event in events)
        assert db.get(User, user_id).marketing_consent_active is False
    assert recorded["marketing_test_selected"] is True


def test_production_without_published_pack_fails_closed(client, monkeypatch, SessionLocal):
    monkeypatch.setattr(settings, "runtime_env", "production")
    pack = client.get("/legal/pack").json()
    assert pack["registration_available"] is False
    assert pack["acceptance_effect"] == "unavailable"
    response = client.post("/auth/register", json={
        "email": "closed-legal@booker.test", "password": "password1", "full_name": "Closed",
        "accept_offer": True, "accept_privacy": True,
        "accept_processing": True,
        "accepted_documents": _accepted(pack),
    })
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="closed-legal@booker.test").count() == 0


def test_withdrawal_is_private_append_only_and_does_not_erase_required_history(client, SessionLocal):
    pack = client.get("/legal/pack").json()
    response = client.post("/auth/register", json={
        "email": "withdraw-legal@booker.test", "password": "password1", "full_name": "Withdraw",
        "accept_offer": True, "accept_privacy": True, "marketing_opt_in": True,
        "accept_processing": True,
        "accepted_documents": _accepted(pack), "draft_test_acknowledgement": True,
    })
    user = response.json()
    other = register(client, "other-legal@booker.test")
    assert client.get("/me/consents").status_code == 401
    mine = client.get("/me/consents", headers=auth_header(user["token"])).json()
    theirs = client.get("/me/consents", headers=auth_header(other["token"])).json()
    assert len(mine["history"]) == 4
    assert len(theirs["history"]) == 3
    assert client.post("/me/consents/marketing/withdraw", headers=auth_header(other["token"])).json() == {
        "marketing_email_active": False, "marketing_test_selected": False,
    }
    assert client.post("/me/consents/marketing/withdraw", headers=auth_header(user["token"])).status_code == 200
    assert client.post("/me/consents/marketing/withdraw", headers=auth_header(user["token"])).status_code == 200
    after = client.get("/me/consents", headers=auth_header(user["token"])).json()
    assert after["marketing_email_active"] is False
    assert after["marketing_test_selected"] is False
    assert len(after["history"]) == 5
    assert [e["action"] for e in after["history"] if e["kind"] == "marketing_email"] == [
        "accepted", "withdrawn",
    ]


def test_reaccept_requires_new_published_current_version(client, SessionLocal, monkeypatch):
    user = register(client, "reaccept-legal@booker.test")
    headers = auth_header(user["token"])
    draft = client.get("/legal/pack").json()
    assert client.post("/me/consents/reaccept", json=_reaccept(draft),
                       headers=headers).status_code == 409
    with SessionLocal() as db:
        for key in ("offer", "privacy", "consent_texts", "cookies", "disputes", "suppliers", "cancellation"):
            old = db.query(LegalDocumentVersion).filter_by(key=key, version="2026-10-01-draft").one()
            db.add(LegalDocumentVersion(key=key, version="approved-test-v2", content_hash=old.content_hash,
                                        status="published", source_path=old.source_path,
                                        published_at=utcnow()))
        db.commit()
    published = client.get("/legal/pack").json()
    assert published["status"] == "published"
    monkeypatch.setattr(settings, "runtime_env", "production")
    assert client.get("/legal/pack").json()["registration_available"] is False
    monkeypatch.setattr(settings, "runtime_env", "local")
    assert client.post("/me/consents/reaccept", json=_reaccept(draft),
                       headers=headers).status_code == 409
    assert client.post("/me/consents/reaccept", json={"accepted_documents": _accepted(published)},
                       headers=headers).status_code == 422
    ok = client.post("/me/consents/reaccept", json=_reaccept(published),
                     headers=headers)
    assert ok.status_code == 200, ok.text
    assert client.post("/me/consents/reaccept", json=_reaccept(published),
                       headers=headers).status_code == 409
    with SessionLocal() as db:
        events = db.query(ConsentEvent).filter_by(user_id=user["user_id"], kind="offer").all()
        assert {event.document_version for event in events} == {"2026-10-01-draft", "approved-test-v2"}


@pytest.mark.parametrize("mismatch_key", ["privacy", "cookies"])
def test_mixed_published_versions_fail_closed_even_for_direct_client(client, SessionLocal, mismatch_key):
    with SessionLocal() as db:
        for key in ("offer", "privacy", "consent_texts", "cookies", "disputes", "suppliers", "cancellation"):
            old = db.query(LegalDocumentVersion).filter_by(key=key, version="2026-10-01-draft").one()
            version = "test-v3" if key == mismatch_key else "test-v2"
            db.add(LegalDocumentVersion(key=key, version=version, content_hash=old.content_hash,
                                        status="published", source_path=old.source_path,
                                        published_at=utcnow()))
        db.commit()
    pack = client.get("/legal/pack").json()
    assert pack["status"] == "unavailable"
    assert pack["registration_available"] is False
    response = client.post("/auth/register", json={
        "email": "mixed-pack@booker.test", "password": "password1", "full_name": "Mixed",
        "accept_offer": True, "accept_privacy": True, "accept_processing": True,
        "accepted_documents": _accepted(pack),
    })
    assert response.status_code == 503


def test_legacy_audit_is_reported_unknown_without_forging_new_consent(client, SessionLocal):
    from booker_api.security import hash_password, issue_token

    with SessionLocal() as db:
        user = User(email="legacy-legal@booker.test", full_name="Legacy",
                    password_hash=hash_password("password1"))
        db.add(user)
        db.flush()
        db.add(AuditLog(actor_user_id=user.id, action="user.registered", entity_type="user",
                        entity_id=user.id, payload='{"legal_pack_version":"2026-08-18-draft"}'))
        token = issue_token(db, user)
        db.commit()
        user_id = user.id
    response = client.get("/me/consents", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["legacy_evidence_status"] == "legacy_unknown"
    assert response.json()["history"] == []
    with SessionLocal() as db:
        assert db.query(ConsentEvent).filter_by(user_id=user_id).count() == 0
