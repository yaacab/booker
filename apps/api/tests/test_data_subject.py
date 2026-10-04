"""P0-F: bounded subject requests, legal holds and optional processing restriction."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from alembic import command
from booker_api.data_subject_lock import lock_subject
from booker_api.db import Base, enable_sqlite_foreign_keys
from booker_api.models import DataSubjectRequest, LegalHold, SavedSearch, User
from tests.conftest import auth_header, register
from tests.postgres_harness import isolated_postgres_schema
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


def _new_request(client, user, request_type="delete", key="subject-request-key-1", **extra):
    return client.post(
        "/data-subject/requests", json={"request_type": request_type, **extra},
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )


def _admin(client):
    return _promote_admin(client, "privacy-admin@booker.test", totp=TEST_TOTP_SECRET)


def _transition(client, admin, request_id, version, target, reason="review_started"):
    return client.post(
        f"/admin/data-subject/requests/{request_id}/transition",
        json={"status": target, "decision_reason_code": reason},
        headers={**admin_totp_headers(admin["token"]), "If-Match": str(version)},
    )


def test_request_replay_idor_cancel_and_disabled_export(client):
    owner = register(client, "privacy-owner@booker.test")
    other = register(client, "privacy-other@booker.test")
    assert client.post("/data-subject/requests", json={
        "request_type": "delete", "instructions": "delete all now",
    }, headers={**auth_header(owner["token"]), "Idempotency-Key": "invalid-instructions-key"}).status_code == 422
    assert _new_request(client, owner, "correct", key="invalid-correction-key").status_code == 422
    created = _new_request(client, owner, "export")
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["status"] == "pending" and row["state_version"] == 0
    assert len(row["events"]) == 1
    replay = _new_request(client, owner, "export")
    assert replay.status_code == 201 and replay.json()["id"] == row["id"]
    assert _new_request(client, owner, "delete").status_code == 409
    assert _new_request(client, other, "export").status_code == 201
    assert client.get(f"/data-subject/requests/{row['id']}", headers=auth_header(other["token"])).status_code == 404
    assert client.post(f"/data-subject/requests/{row['id']}/cancel",
                       headers={**auth_header(other["token"]), "If-Match": "0"}).status_code == 404
    assert client.get(f"/data-subject/requests/{row['id']}/export-manifest",
                      headers=auth_header(other["token"])).status_code == 404
    manifest = client.get(f"/data-subject/requests/{row['id']}/export-manifest",
                          headers=auth_header(owner["token"])).json()
    assert manifest["generator_enabled"] is False and manifest["download_url"] is None
    assert "password" not in str(manifest).lower() and "support" not in str(manifest).lower()
    cancelled = client.post(f"/data-subject/requests/{row['id']}/cancel",
                            headers={**auth_header(owner["token"]), "If-Match": "0"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert len(cancelled.json()["events"]) == 2
    assert client.post(f"/data-subject/requests/{row['id']}/cancel",
                       headers={**auth_header(owner["token"]), "If-Match": "0"}).status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.query(DataSubjectRequest).filter_by(subject_user_id=owner["user_id"]).count() == 1


def test_admin_step_up_cas_self_decision_hold_and_dry_run(client):
    owner = register(client, "privacy-delete@booker.test")
    admin = _admin(client)
    row = _new_request(client, owner).json()
    path = f"/admin/data-subject/requests/{row['id']}"
    assert client.get(path, headers=auth_header(owner["token"])).status_code == 403
    assert client.get(path, headers=auth_header(admin["pre_promotion_token"])).status_code == 403
    assert client.get(path, headers=admin_totp_headers(admin["token"])).status_code == 200
    review = _transition(client, admin, row["id"], 0, "in_review")
    assert review.status_code == 200, review.text
    assert _transition(client, admin, row["id"], 1, "approved", "scope_rejected").status_code == 422
    assert _transition(client, admin, row["id"], 0, "approved", "scope_accepted").status_code == 409
    hold = client.post("/admin/legal-holds",
                       json={"subject_user_id": owner["user_id"], "reason_code": "dispute"},
                       headers=admin_totp_headers(admin["token"]))
    assert hold.status_code == 201, hold.text
    assert client.post("/admin/legal-holds",
                       json={"subject_user_id": owner["user_id"], "reason_code": "financial_review"},
                       headers=admin_totp_headers(admin["token"])).status_code == 409
    plan = client.get(f"{path}/deletion-plan", headers=admin_totp_headers(admin["token"]))
    assert plan.status_code == 200
    assert plan.json()["dry_run"] and not plan.json()["executor_enabled"]
    assert plan.json()["blocked"] and "active_legal_hold" in plan.json()["block_reasons"]
    assert "privacy-delete@" not in str(plan.json())
    assert _transition(client, admin, row["id"], 1, "approved", "scope_accepted").status_code == 409
    assert client.get("/admin/legal-holds", params={"subject_user_id": owner["user_id"]},
                      headers=auth_header(owner["token"])).status_code == 403
    assert "legal_hold" not in str(client.get(f"/data-subject/requests/{row['id']}",
                                          headers=auth_header(owner["token"])).json()).lower()
    release = client.post(f"/admin/legal-holds/{hold.json()['id']}/release",
                          headers=admin_totp_headers(admin["token"]))
    assert release.status_code == 200 and release.json()["released_at"]
    approved = _transition(client, admin, row["id"], 1, "approved", "scope_accepted")
    assert approved.status_code == 200 and approved.json()["state_version"] == 2
    assert _transition(client, admin, row["id"], 2, "completed", "scope_accepted").status_code == 409
    later_hold = client.post("/admin/legal-holds",
                             json={"subject_user_id": owner["user_id"], "reason_code": "security_incident"},
                             headers=admin_totp_headers(admin["token"]))
    assert later_hold.status_code == 201
    suspended = client.get(path, headers=admin_totp_headers(admin["token"]))
    assert suspended.json()["status"] == "in_review" and suspended.json()["state_version"] == 3
    assert suspended.json()["events"][-1]["reason_code"] == "policy_pending"
    assert client.post(f"/data-subject/requests/{row['id']}/cancel",
                       headers={**auth_header(owner["token"]), "If-Match": "3"}).status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.query(LegalHold).filter_by(subject_user_id=owner["user_id"]).count() == 2
        with pytest.raises(DatabaseError):
            db.execute(text("DELETE FROM data_subject_request_events WHERE request_id = :id"), {"id": row["id"]})
            db.commit()


def test_restriction_disables_optional_search_notifications_and_self_approval(client):
    owner = register(client, "privacy-restrict@booker.test")
    admin = _admin(client)
    owner_headers = auth_header(owner["token"])
    org = client.post("/orgs", json={"name": "Private customer", "kind": "customer"}, headers=owner_headers).json()
    owner_headers["X-Booker-Org"] = org["id"]
    saved = client.post("/saved-searches", json={
        "name": "Согласованный поиск", "organization_id": org["id"],
        "query_params": {"city": "Москва"}, "notify_consent": True, "consent": True,
    }, headers=owner_headers)
    assert saved.status_code == 201 and saved.json()["notify_consent"] is True
    row = _new_request(client, owner, "restrict").json()
    assert _transition(client, admin, row["id"], 0, "in_review").status_code == 200
    assert _transition(client, admin, row["id"], 1, "approved", "scope_accepted").status_code == 200
    with client.app.state.SessionLocal() as db:
        assert db.get(User, owner["user_id"]).optional_processing_restricted is True
        assert db.get(SavedSearch, saved.json()["id"]).notify_consent is False
    assert client.patch(f"/saved-searches/{saved.json()['id']}/notify-consent",
                        json={"notify_consent": True, "consent": True}, headers=owner_headers).status_code == 409
    assert client.post("/saved-searches", json={
        "name": "Ещё поиск", "organization_id": org["id"],
        "query_params": {"city": "Москва"}, "notify_consent": True, "consent": True,
    }, headers=owner_headers).status_code == 409
    assert _transition(client, admin, row["id"], 2, "completed", "scope_accepted").status_code == 200

    self_request = _new_request(client, admin, "restrict", key="admin-own-subject-key").json()
    assert _transition(client, admin, self_request["id"], 0, "in_review").status_code == 200
    assert _transition(client, admin, self_request["id"], 1, "approved", "scope_accepted").status_code == 403


def test_subject_request_migration_upgrade_and_downgrade_sqlite(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'subject-migration.db'}"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "fc8f901ab2c3")
    engine = create_engine(db_url)
    assert "data_subject_requests" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "fd9a012bc3d4")
    assert {"data_subject_requests", "data_subject_request_events", "legal_holds"} <= set(inspect(engine).get_table_names())
    assert "optional_processing_restricted" in {c["name"] for c in inspect(engine).get_columns("users")}
    command.downgrade(cfg, "fc8f901ab2c3")
    assert "data_subject_requests" not in inspect(engine).get_table_names()
    assert "optional_processing_restricted" not in {c["name"] for c in inspect(engine).get_columns("users")}
    engine.dispose()


def test_subject_mutations_serialize_on_same_user_sqlite(tmp_path):
    engine = enable_sqlite_foreign_keys(create_engine(f"sqlite:///{tmp_path / 'subject-lock.db'}"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id="locked-subject", email="locked@booker.test", full_name="Locked",
                    password_hash="unused"))
        db.commit()
    started = Event()
    acquired = Event()

    def competing_mutation():
        with Session(engine) as db:
            started.set()
            assert lock_subject(db, "locked-subject") is not None
            acquired.set()
            db.commit()

    with Session(engine) as first:
        assert lock_subject(first, "locked-subject") is not None
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(competing_mutation)
            assert started.wait(2)
            assert not acquired.wait(0.2)
            first.commit()
            result.result(timeout=3)
    assert acquired.is_set()
    engine.dispose()


@pytest.mark.postgres_integration
def test_subject_request_migration_postgres_opt_in():
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: subject migration not tested on real PostgreSQL")
    with isolated_postgres_schema(dsn) as (engine, cfg, _schema):
        command.upgrade(cfg, "fc8f901ab2c3")
        command.upgrade(cfg, "fd9a012bc3d4")
        assert {"data_subject_requests", "data_subject_request_events", "legal_holds"} <= set(inspect(engine).get_table_names())
        command.downgrade(cfg, "fc8f901ab2c3")
        assert "data_subject_requests" not in inspect(engine).get_table_names()
