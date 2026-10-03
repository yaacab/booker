import hashlib
from datetime import timedelta

from booker_api.models import PasswordResetToken, SessionToken
from booker_api.security import hash_password, now, verify_password
from tests.conftest import auth_header, publish_artist, register


def test_password_verifier_rejects_accounts_without_local_credentials():
    password = "known-password"
    assert verify_password(password, hash_password(password))
    assert not verify_password(password, None)
    assert not verify_password(password, "")
    assert not verify_password(password, "malformed")


def test_membership_changes_and_active_org_switch_require_target_org_authority(client):
    owner = register(client, "matrix-owner@booker.test", "Owner")
    foreign_owner = register(client, "matrix-foreign@booker.test", "Foreign")
    viewer = register(client, "matrix-viewer@booker.test", "Viewer")
    candidate = register(client, "matrix-candidate@booker.test", "Candidate")
    owner_headers = auth_header(owner["token"])
    org = client.post(
        "/orgs",
        json={"name": "Matrix Team", "kind": "artist"},
        headers=owner_headers,
    ).json()
    foreign_org = client.post(
        "/orgs",
        json={"name": "Foreign Team", "kind": "artist"},
        headers=auth_header(foreign_owner["token"]),
    ).json()
    assert client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=owner_headers,
    ).status_code == 200

    for actor in (foreign_owner, viewer):
        denied = client.post(
            f"/orgs/{org['id']}/members",
            json={"user_id": candidate["user_id"], "role": "owner", "can_confirm_offer": True},
            headers=auth_header(actor["token"]),
        )
        assert denied.status_code == 403
        assert client.get(
            f"/orgs/{org['id']}", headers=auth_header(actor["token"])
        ).status_code == (403 if actor == foreign_owner else 200)

    denied_switch = client.post(
        "/me/active-org",
        json={"organization_id": foreign_org["id"]},
        headers=auth_header(viewer["token"]),
    )
    assert denied_switch.status_code == 403
    assert client.get("/me", headers=auth_header(viewer["token"])).json()[
        "active_organization_id"
    ] != foreign_org["id"]
    assert client.get(f"/orgs/{org['id']}", headers=owner_headers).json()["members"] == [
        {"user_id": owner["user_id"], "role": "owner", "can_confirm_offer": True},
        {"user_id": viewer["user_id"], "role": "viewer", "can_confirm_offer": False},
    ]


def test_password_reset_consumes_token_and_revokes_existing_sessions(client, SessionLocal):
    user = register(client, "reset-sessions@booker.test", "Reset Owner")
    second_login = client.post(
        "/auth/login",
        json={"email": "reset-sessions@booker.test", "password": "password1"},
    )
    assert second_login.status_code == 200
    raw = "reset-token-with-sufficient-entropy-for-test"
    older = "older-reset-token-with-sufficient-entropy-for-test"
    with SessionLocal() as db:
        for token in (raw, older):
            db.add(PasswordResetToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user["user_id"],
                expires_at=now() + timedelta(hours=1),
            ))
        db.commit()
    changed = client.post(
        "/auth/recover/confirm",
        json={"token": raw, "password": "new-password123"},
    )
    assert changed.status_code == 200
    for token in (user["token"], second_login.json()["token"]):
        assert client.get("/me", headers=auth_header(token)).status_code == 401
    assert client.post(
        "/auth/recover/confirm",
        json={"token": raw, "password": "another-password123"},
    ).status_code == 400
    assert client.post(
        "/auth/recover/confirm",
        json={"token": older, "password": "another-password123"},
    ).status_code == 400
    assert client.post(
        "/auth/login",
        json={"email": "reset-sessions@booker.test", "password": "new-password123"},
    ).status_code == 200


def test_sqlite_login_waits_for_password_reset_before_checking_old_password(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from booker_api.db import Base, get_db
    from booker_api.legal_registry import seed_draft_versions
    from booker_api.routers import identity, legal

    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, future=True)
    with session_local() as db:
        seed_draft_versions(db)
        db.commit()
    app = FastAPI()
    app.include_router(identity.router)
    app.include_router(legal.router)

    def override_db():
        with session_local() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as http:
        user = register(http, "race-reset@booker.test", "Race")
        raw = "concurrent-reset-token-with-sufficient-entropy"
        with session_local() as db:
            db.add(PasswordResetToken(
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                user_id=user["user_id"],
                expires_at=now() + timedelta(hours=1),
            ))
            db.commit()

        reset_ready = Event()
        release_reset = Event()
        login_started = Event()
        password_checked = Event()
        real_audit = identity.audit
        real_verify = identity.verify_password

        def paused_audit(*args, **kwargs):
            if kwargs.get("action") == "auth.password_reset_completed":
                reset_ready.set()
                assert release_reset.wait(5)
            return real_audit(*args, **kwargs)

        def tracked_verify(*args, **kwargs):
            password_checked.set()
            return real_verify(*args, **kwargs)

        monkeypatch.setattr(identity, "audit", paused_audit)
        monkeypatch.setattr(identity, "verify_password", tracked_verify)

        def concurrent_login():
            login_started.set()
            return http.post(
                "/auth/login",
                json={"email": "race-reset@booker.test", "password": "password1"},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            reset = pool.submit(
                http.post,
                "/auth/recover/confirm",
                json={"token": raw, "password": "new-password123"},
            )
            try:
                assert reset_ready.wait(5)
                login = pool.submit(concurrent_login)
                assert login_started.wait(5)
                assert not password_checked.wait(0.2)
            finally:
                release_reset.set()
            assert reset.result(timeout=5).status_code == 200
            assert login.result(timeout=5).status_code == 401
        with session_local() as db:
            assert db.query(SessionToken).filter_by(user_id=user["user_id"]).count() == 0


def test_register_requires_legal_accept(client, SessionLocal):
    from booker_api.models import User

    denied = client.post(
        "/auth/register",
        json={"email": "nolegal@booker.test", "password": "password1", "full_name": "X"},
    )
    assert denied.status_code == 422
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="nolegal@booker.test").count() == 0
    ok = client.post(
        "/auth/register",
        json={
            "email": "legalok@booker.test",
            "password": "password1",
            "full_name": "X",
            "accept_offer": True,
            "accept_privacy": True,
            "accept_processing": True,
            "marketing_opt_in": False,
            "accepted_documents": [
                {k: doc[k] for k in ("key", "version", "content_hash")}
                for doc in client.get("/legal/pack").json()["documents"] if doc["required"]
            ],
            "draft_test_acknowledgement": True,
        },
    )
    assert ok.status_code == 200


def test_recover_does_not_reveal_email(client):
    register(client, "a@booker.test", "A")
    missing = client.post("/auth/recover", json={"email": "nobody@booker.test"})
    exists = client.post("/auth/recover", json={"email": "a@booker.test"})
    assert missing.status_code == 200
    assert exists.status_code == 200
    assert missing.json()["ok"] is True
    assert exists.json()["ok"] is True
    assert missing.json() == exists.json()


def test_anonymous_logout_does_not_revoke_another_session(client):
    user = register(client, "logout-anonymous@booker.test", "Owner")
    denied = client.post("/auth/logout")
    assert denied.status_code == 401
    still_active = client.get("/me", headers=auth_header(user["token"]))
    assert still_active.status_code == 200


def test_me_ignores_foreign_org_header_without_leaking_membership(client):
    owner = register(client, "me-owner@booker.test", "Owner")
    outsider = register(client, "me-outsider@booker.test", "Outsider")
    org = client.post(
        "/orgs", json={"name": "Private Me", "kind": "customer"},
        headers=auth_header(owner["token"]),
    ).json()
    response = client.get(
        "/me", headers={**auth_header(outsider["token"]), "X-Booker-Org": org["id"]}
    )
    assert response.status_code == 200
    assert response.json()["active_organization_id"] != org["id"]
    assert org["id"] not in {row["id"] for row in response.json()["organizations"]}


def test_anonymous_org_creation_has_no_side_effects(client, SessionLocal):
    from booker_api.models import Organization, TeamMember

    with SessionLocal() as db:
        before = (db.query(Organization).count(), db.query(TeamMember).count())
    denied = client.post("/orgs", json={"name": "Anonymous", "kind": "customer"})
    assert denied.status_code == 401
    with SessionLocal() as db:
        assert (db.query(Organization).count(), db.query(TeamMember).count()) == before


def test_cannot_read_foreign_org(client):
    a = register(client, "a@booker.test", "A")
    b = register(client, "b@booker.test", "B")
    org = client.post(
        "/orgs",
        json={"name": "A Org", "kind": "customer"},
        headers=auth_header(a["token"]),
    )
    assert org.status_code == 200
    foreign = client.get(f"/orgs/{org.json()['id']}", headers=auth_header(b["token"]))
    assert foreign.status_code == 403


def test_member_without_confirm_cannot_ack_offer(client):
    customer = register(client, "cust@booker.test", "Cust")
    owner = register(client, "owner@booker.test", "Owner")
    manager = register(client, "mgr@booker.test", "Mgr")

    cust_org = client.post(
        "/orgs",
        json={"name": "Клиент", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Артисты", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    add = client.post(
        f"/orgs/{artist_org['id']}/members",
        json={"user_id": manager["user_id"], "role": "manager", "can_confirm_offer": False},
        headers=auth_header(owner["token"]),
    )
    assert add.status_code == 200

    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    ).json()
    publish_artist(client, owner, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Свадьба",
            "event_date": starts.isoformat(),
        },
        headers=auth_header(customer["token"]),
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=auth_header(customer["token"]),
    ).json()
    denied = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"]},
        headers=auth_header(manager["token"]),
    )
    assert denied.status_code == 403
