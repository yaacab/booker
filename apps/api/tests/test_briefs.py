from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, publish_artist, publish_venue, register


def _setup_parties(client):
    customer = register(client, "c-brief@booker.test", "Заказчик")
    artist = register(client, "a-brief@booker.test", "Артист")
    venue = register(client, "v-brief@booker.test", "Площадка")
    ch = auth_header(customer["token"])
    ah = auth_header(artist["token"])
    vh = auth_header(venue["token"])
    cust_org = client.post(
        "/orgs",
        json={"name": "Свадьба ООО", "kind": "customer"},
        headers=ch,
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "DJ Crew", "kind": "artist"},
        headers=ah,
    ).json()
    venue_org = client.post(
        "/orgs",
        json={"name": "Зал Лофт", "kind": "venue"},
        headers=vh,
    ).json()
    artist_profile = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Brief", "category": "dj"},
        headers=ah,
    ).json()
    venue_profile = client.post(
        "/venues",
        json={"organization_id": venue_org["id"], "name": "Зал Brief", "capacity": 100},
        headers=vh,
    ).json()
    starts = datetime.now(timezone.utc) + timedelta(days=10)
    for resource_type, resource_id, headers in (
        ("artist", artist_profile["id"], ah),
        ("hall", venue_profile["hall_id"], vh),
    ):
        slot = client.post(
            "/slots",
            json={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=4)).isoformat(),
            },
            headers=headers,
        )
        assert slot.status_code == 200, slot.text
    publish_artist(client, artist, artist_profile["id"])
    publish_venue(client, venue, venue_profile["id"])
    return {
        "customer": customer,
        "artist": artist,
        "venue": venue,
        "ch": ch,
        "ah": ah,
        "vh": vh,
        "cust_org": cust_org,
        "artist_org": artist_org,
        "artist_profile": artist_profile,
        "venue_org": venue_org,
    }


def _publish_payload(cust_org_id: str, **extra):
    body = {
        "organization_id": cust_org_id,
        "title": "Нужен DJ на корпоратив",
        "city": "Москва",
        "date_from": "2026-10-01T18:00:00+00:00",
        "date_to": "2026-10-01T23:00:00+00:00",
        "role_needed": "dj",
        "guest_count_band": "51-100",
        "public_notes": "Вечерний сет, без алкоголя в райдере",
    }
    body.update(extra)
    return body


def _assert_no_pii(payload: dict):
    forbidden_keys = {
        "phone",
        "email",
        "budget",
        "budget_rub",
        "guest_count",
        "notes",
        "event_id",
        "created_by_user_id",
    }
    assert not (forbidden_keys & set(payload.keys()))
    assert "guest_count_band" in payload
    blob = str(payload)
    assert "+7900" not in blob
    assert "@booker.test" not in blob.lower()
    assert "secret@private.test" not in blob.lower()
    assert "350000" not in blob


def test_brief_cannot_link_another_customers_private_event(client):
    ctx = _setup_parties(client)
    other = register(client, "foreign-brief-event@booker.test", "Other customer")
    other_headers = auth_header(other["token"])
    other_org = client.post(
        "/orgs", json={"name": "Other Customer", "kind": "customer"}, headers=other_headers
    )
    assert other_org.status_code == 200
    event = client.post(
        "/events",
        json={
            "organization_id": other_org.json()["id"],
            "title": "Чужое событие",
            "event_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "requirements": [{"category_code": "dj", "qty": 1, "required": True}],
        },
        headers=other_headers,
    )
    assert event.status_code == 200, event.text
    denied = client.post(
        "/briefs",
        json=_publish_payload(ctx["cust_org"]["id"], event_id=event.json()["id"]),
        headers=ctx["ch"],
    )
    assert denied.status_code == 403


def test_publish_list_respond_close(client):
    ctx = _setup_parties(client)
    published = client.post(
        "/briefs",
        json=_publish_payload(ctx["cust_org"]["id"]),
        headers=ctx["ch"],
    )
    assert published.status_code == 200, published.text
    brief = published.json()
    assert brief["status"] == "open"
    assert brief["role_needed"] == "dj"
    assert brief["guest_count_band"] == "51-100"
    assert brief["title"] == "Нужен DJ на корпоратив"
    _assert_no_pii(brief)
    assert "event_id" not in brief
    assert "created_by_user_id" not in brief

    listed = client.get("/briefs")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == brief["id"]
    _assert_no_pii(items[0])

    role_filtered = client.get("/briefs", params={"role_needed": "dj"})
    assert len(role_filtered.json()["items"]) == 1

    got = client.get(f"/briefs/{brief['id']}")
    assert got.status_code == 200
    _assert_no_pii(got.json())

    response = client.post(
        f"/briefs/{brief['id']}/responses",
        json={
            "supplier_org_id": ctx["artist_org"]["id"],
            "message": "Готов взять сет",
        },
        headers=ctx["ah"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["brief_id"] == brief["id"]
    assert body["supplier_org_id"] == ctx["artist_org"]["id"]
    assert body["message"] == "Готов взять сет"
    assert body["status"] == "interested"
    # No booking auto-created — response payload has no booking_id.
    assert "booking_id" not in body

    dup = client.post(
        f"/briefs/{brief['id']}/responses",
        json={"supplier_org_id": ctx["artist_org"]["id"], "message": "ещё раз"},
        headers=ctx["ah"],
    )
    assert dup.status_code == 409

    venue_resp = client.post(
        f"/briefs/{brief['id']}/responses",
        json={"supplier_org_id": ctx["venue_org"]["id"], "message": "Есть зал"},
        headers=ctx["vh"],
    )
    assert venue_resp.status_code == 200, venue_resp.text

    owner_list = client.get(f"/briefs/{brief['id']}/responses", headers=ctx["ch"])
    assert owner_list.status_code == 200
    assert len(owner_list.json()["items"]) == 2

    stranger_list = client.get(f"/briefs/{brief['id']}/responses", headers=ctx["ah"])
    assert stranger_list.status_code == 403

    closed = client.post(f"/briefs/{brief['id']}/close", headers=ctx["ch"])
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None
    _assert_no_pii(closed.json())

    open_list = client.get("/briefs")
    assert open_list.json()["items"] == []

    after_close = client.post(
        f"/briefs/{brief['id']}/responses",
        json={"supplier_org_id": ctx["artist_org"]["id"], "message": "поздно"},
        headers=ctx["ah"],
    )
    assert after_close.status_code == 409


def test_brief_close_rejects_viewer_and_other_tenant_without_state_change(client, SessionLocal):
    from booker_api.models import PublicBrief

    ctx = _setup_parties(client)
    published = client.post(
        "/briefs", json=_publish_payload(ctx["cust_org"]["id"]), headers=ctx["ch"]
    )
    assert published.status_code == 200, published.text
    brief_id = published.json()["id"]
    viewer = register(client, "brief-viewer@booker.test", "Наблюдатель")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=ctx["ch"],
    )
    assert added.status_code == 200, added.text
    for headers in (auth_header(viewer["token"]), ctx["ah"]):
        denied = client.post(f"/briefs/{brief_id}/close", headers=headers)
        assert denied.status_code == 403, denied.text
        with SessionLocal() as db:
            row = db.get(PublicBrief, brief_id)
            assert row.status == "open"
            assert row.closed_at is None


def test_brief_linked_event_does_not_leak_private_fields(client):
    ctx = _setup_parties(client)
    event = client.post(
        "/events",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "title": "Секретный корпоратив",
            "event_date": "2026-10-01T18:00:00+00:00",
            "guest_count": 87,
            "budget_rub": 350000,
            "notes": "Телефон координатора +79001112233, email secret@private.test",
        },
        headers=ctx["ch"],
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    published = client.post(
        "/briefs",
        json=_publish_payload(
            ctx["cust_org"]["id"],
            event_id=event_id,
            title="Публичный снимок",
            public_notes="Нужен ведущий",
        ),
        headers=ctx["ch"],
    )
    assert published.status_code == 200, published.text
    brief = published.json()
    _assert_no_pii(brief)
    assert "budget_rub" not in brief
    assert "guest_count" not in brief
    assert "notes" not in brief
    assert "event_id" not in brief
    assert "+79001112233" not in str(brief)
    assert "secret@private.test" not in str(brief)
    assert "350000" not in str(brief)

    listed = client.get("/briefs").json()["items"][0]
    _assert_no_pii(listed)
    assert "budget_rub" not in listed
    assert "notes" not in listed
    assert "event_id" not in listed

    detail = client.get(f"/briefs/{brief['id']}")
    assert detail.status_code == 200
    _assert_no_pii(detail.json())
    assert event_id not in detail.text
    assert "+79001112233" not in detail.text
    assert "secret@private.test" not in detail.text


def test_customer_cannot_respond_as_customer_org(client):
    ctx = _setup_parties(client)
    brief = client.post(
        "/briefs",
        json=_publish_payload(ctx["cust_org"]["id"]),
        headers=ctx["ch"],
    ).json()
    res = client.post(
        f"/briefs/{brief['id']}/responses",
        json={"supplier_org_id": ctx["cust_org"]["id"], "message": "сам себе"},
        headers=ctx["ch"],
    )
    assert res.status_code == 403


def test_artist_cannot_publish_brief(client):
    ctx = _setup_parties(client)
    res = client.post(
        "/briefs",
        json=_publish_payload(ctx["artist_org"]["id"]),
        headers=ctx["ah"],
    )
    assert res.status_code == 403


def test_unpublished_supplier_cannot_respond_to_brief(client):
    ctx = _setup_parties(client)
    brief = client.post(
        "/briefs", json=_publish_payload(ctx["cust_org"]["id"]), headers=ctx["ch"]
    ).json()
    disabled = client.put(
        f"/artists/{ctx['artist_profile']['id']}/publication",
        json={"enabled": False, "state_version": 1},
        headers=ctx["ah"],
    )
    assert disabled.status_code == 200
    denied = client.post(
        f"/briefs/{brief['id']}/responses",
        json={"supplier_org_id": ctx["artist_org"]["id"], "message": "Я готов"},
        headers=ctx["ah"],
    )
    assert denied.status_code == 409


def test_invalid_guest_count_band(client):
    ctx = _setup_parties(client)
    res = client.post(
        "/briefs",
        json=_publish_payload(ctx["cust_org"]["id"], guest_count_band="exactly-87"),
        headers=ctx["ch"],
    )
    assert res.status_code == 400
