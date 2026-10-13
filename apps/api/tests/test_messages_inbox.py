"""W4-MSG-HUB: message inbox across deal rooms."""

from datetime import datetime, timedelta, timezone

from booker_api.security import now
from tests.conftest import auth_header, publish_artist, register


def test_legacy_request_without_conversation_remains_in_supplier_list(client):
    from booker_api.models import Request
    from tests.test_offers import setup_negotiation

    ctx = setup_negotiation(client)
    with client.app.state.SessionLocal() as db:
        legacy = Request(
            event_id=ctx["event"]["id"],
            resource_type="artist",
            resource_id=ctx["artist"]["id"],
            supplier_org_id=ctx["artist_org"]["id"],
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
    listed = client.get(
        "/requests",
        params={"organization_id": ctx["artist_org"]["id"]},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert listed.status_code == 200
    assert legacy_id in {item["id"] for item in listed.json()["items"]}
    # Legacy rows have no immutable participant snapshot. Publishing an offer
    # remains closed until the historical parties are reconciled.
    blocked_offer = client.post(
        f"/requests/{legacy_id}/offers",
        json={"honorarium_rub": 60000, "slot_id": ctx["slot"]["id"]},
        headers=auth_header(ctx["owner"]["token"]),
    )
    assert blocked_offer.status_code == 409


def _deal_ctx(client):
    customer = register(client, "msg-cust@booker.test", "Клиент")
    owner = register(client, "msg-owner@booker.test", "Артист")
    ch = auth_header(customer["token"])
    oh = auth_header(owner["token"])
    cust_org = client.post("/orgs", json={"name": "Клиент MSG", "kind": "customer"}, headers=ch).json()
    artist_org = client.post("/orgs", json={"name": "Шоу MSG", "kind": "artist"}, headers=oh).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Msg", "category": "dj"},
        headers=oh,
    ).json()
    day = (now() + timedelta(days=10)).astimezone().replace(hour=18, minute=0, second=0, microsecond=0)
    starts = day.isoformat()
    ends = (day + timedelta(hours=3)).isoformat()
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=oh,
    ).json()
    publish_artist(client, owner, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Вечер MSG",
            "event_date": starts,
            "requirements": [{"category_code": "dj", "qty": 1}],
        },
        headers=ch,
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": event["requirements"][0]["id"],
        },
        headers=ch,
    ).json()
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 50000, "slot_id": slot["id"]},
        headers=oh,
    ).json()
    return {
        "ch": ch,
        "oh": oh,
        "customer_user_id": customer["user_id"],
        "customer_org_id": cust_org["id"],
        "supplier_org_id": artist_org["id"],
        "booking_id": offer["booking_id"],
        "stranger": auth_header(register(client, "msg-x@booker.test", "Чужой")["token"]),
    }


def test_messages_inbox_lists_accessible_threads(client):
    ctx = _deal_ctx(client)
    posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Привет из deal room", "idempotency_key": "deal-message-1"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text
    inbox = client.get("/messages/inbox", headers=ctx["ch"])
    assert inbox.status_code == 200, inbox.text
    items = inbox.json()["items"]
    assert any(i["booking_id"] == ctx["booking_id"] for i in items)
    hit = next(i for i in items if i["booking_id"] == ctx["booking_id"])
    assert hit["deal_path"] == f"/deals/{ctx['booking_id']}"
    assert hit["last_message"]["body"].startswith("Привет")

    supply = client.get("/messages/inbox", headers=ctx["oh"])
    assert supply.status_code == 200
    assert any(i["booking_id"] == ctx["booking_id"] for i in supply.json()["items"])

    empty = client.get("/messages/inbox", headers=ctx["stranger"])
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_mark_read_is_idempotent_across_repeated_tabs(client, SessionLocal):
    from booker_api.models import ConversationReadState

    ctx = _deal_ctx(client)
    headers = {**ctx["ch"], "X-Booker-Org": ctx["customer_org_id"]}
    item = next(
        candidate
        for candidate in client.get("/messages/inbox", headers=headers).json()["items"]
        if candidate["booking_id"] == ctx["booking_id"]
    )

    responses = [
        client.post(f"/conversations/{item['conversation_id']}/read", headers=headers)
        for _index in range(8)
    ]
    assert [response.status_code for response in responses] == [200] * 8
    with SessionLocal() as db:
        states = (
            db.query(ConversationReadState)
            .filter_by(
                conversation_id=item["conversation_id"],
                user_id=ctx["customer_user_id"],
                organization_id=ctx["customer_org_id"],
            )
            .all()
        )
    assert len(states) == 1


def test_outsider_cannot_mark_conversation_read_or_select_foreign_inbox(client, SessionLocal):
    from booker_api.models import ConversationReadState

    ctx = _deal_ctx(client)
    item = next(
        candidate for candidate in client.get("/messages/inbox", headers=ctx["ch"]).json()["items"]
        if candidate["booking_id"] == ctx["booking_id"]
    )
    denied = client.post(
        f"/conversations/{item['conversation_id']}/read", headers=ctx["stranger"]
    )
    assert denied.status_code == 404, denied.text
    foreign_inbox = client.get(
        "/messages/inbox",
        headers={**ctx["stranger"], "X-Booker-Org": ctx["customer_org_id"]},
    )
    assert foreign_inbox.status_code == 403
    with SessionLocal() as db:
        assert db.query(ConversationReadState).filter_by(
            conversation_id=item["conversation_id"]
        ).count() == 0


def test_inbox_orders_by_server_receipt_when_display_timestamp_is_historical(
    client, SessionLocal
):
    from booker_api.models import Booking, Conversation, Event, Message, Offer, Request

    ctx = _deal_ctx(client)
    with SessionLocal() as db:
        booking = db.get(Booking, ctx["booking_id"])
        original_request = db.get(Request, db.get(Offer, booking.offer_id).request_id)
        old_event = Event(
            organization_id=ctx["customer_org_id"], title="Старый запрос",
            event_date=datetime.now(timezone.utc) + timedelta(days=20),
        )
        db.add(old_event)
        db.flush()
        old_request = Request(
            event_id=old_event.id,
            resource_type=original_request.resource_type,
            resource_id=original_request.resource_id,
            supplier_org_id=ctx["supplier_org_id"],
        )
        db.add(old_request)
        db.flush()
        old_conversation = Conversation(
            request_id=old_request.id,
            customer_org_id=ctx["customer_org_id"],
            supplier_org_id=ctx["supplier_org_id"],
            customer_name_snapshot="Клиент MSG",
            supplier_name_snapshot="Шоу MSG",
            next_message_sequence=2,
        )
        db.add(old_conversation)
        db.flush()
        db.add(Message(
            conversation_id=old_conversation.id, sequence=1, kind="system",
            attribution_status="system", body="Старое сообщение",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
        db.commit()
        old_conversation_id = old_conversation.id
        old_request_id = old_request.id

    posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Новая активность", "idempotency_key": "inbox-order-new"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text
    before = next(
        row for row in client.get("/messages/inbox", headers=ctx["ch"]).json()["items"]
        if row["booking_id"] == ctx["booking_id"]
    )
    with SessionLocal() as db:
        newest = db.get(Message, posted.json()["id"])
        newest.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()

    inbox = client.get("/messages/inbox", headers=ctx["ch"])
    assert inbox.status_code == 200
    items = inbox.json()["items"]
    assert items[0]["booking_id"] == ctx["booking_id"]
    assert items[0]["last_message"]["body"] == "Новая активность"
    assert items[0]["unread_count"] == before["unread_count"]
    assert any(row["conversation_id"] == old_conversation_id for row in items)

    tied_at = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.get(Message, posted.json()["id"]).received_at = tied_at
        old = db.query(Message).filter_by(conversation_id=old_conversation_id).one()
        old.received_at = tied_at
        original = db.get(Request, old_request_id)
        empty_request = Request(
            event_id=original.event_id,
            resource_type=original.resource_type,
            resource_id=original.resource_id,
            supplier_org_id=original.supplier_org_id,
        )
        db.add(empty_request)
        db.flush()
        empty_conversation = Conversation(
            request_id=empty_request.id,
            customer_org_id=ctx["customer_org_id"],
            supplier_org_id=ctx["supplier_org_id"],
            customer_name_snapshot="Клиент MSG",
            supplier_name_snapshot="Шоу MSG",
        )
        db.add(empty_conversation)
        db.commit()
        empty_conversation_id = empty_conversation.id
    tied = client.get("/messages/inbox", headers=ctx["ch"]).json()["items"]
    assert [row["conversation_id"] for row in tied[:2]] == sorted(
        (before["conversation_id"], old_conversation_id), reverse=True
    )
    assert tied[-1]["conversation_id"] == empty_conversation_id


def test_runtime_schema_restart_preserves_unread_sequence_for_backdated_message(
    client, SessionLocal, engine
):
    from booker_api.db import ensure_sqlite_columns
    from booker_api.models import Message

    ctx = _deal_ctx(client)
    supplier_items = client.get("/messages/inbox", headers=ctx["oh"]).json()["items"]
    conversation_id = next(
        row["conversation_id"] for row in supplier_items
        if row["booking_id"] == ctx["booking_id"]
    )
    read = client.post(f"/conversations/{conversation_id}/read", headers=ctx["oh"])
    assert read.status_code == 200
    posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Новое после чтения", "idempotency_key": "inbox-backdated-unread"},
        headers=ctx["ch"],
    )
    assert posted.status_code == 200, posted.text
    with SessionLocal() as db:
        db.get(Message, posted.json()["id"]).created_at = datetime(
            2020, 1, 1, tzinfo=timezone.utc
        )
        db.commit()
    before = next(
        row for row in client.get("/messages/inbox", headers=ctx["oh"]).json()["items"]
        if row["conversation_id"] == conversation_id
    )["unread_count"]
    assert before >= 1
    ensure_sqlite_columns(engine)
    after = next(
        row for row in client.get("/messages/inbox", headers=ctx["oh"]).json()["items"]
        if row["conversation_id"] == conversation_id
    )["unread_count"]
    assert after == before


def test_message_records_acting_organization_and_rejects_ambiguous_dual_member(client):
    ctx = _deal_ctx(client)
    added = client.post(
        f"/orgs/{ctx['supplier_org_id']}/members",
        json={"user_id": ctx["customer_user_id"], "role": "manager"},
        headers=ctx["oh"],
    )
    assert added.status_code == 200, added.text

    ambiguous = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Кто говорит?", "idempotency_key": "dual-message"},
        headers=ctx["ch"],
    )
    assert ambiguous.status_code == 409
    assert "организац" in ambiguous.json()["detail"].lower()

    customer_headers = {**ctx["ch"], "X-Booker-Org": ctx["customer_org_id"]}
    supplier_headers = {**ctx["ch"], "X-Booker-Org": ctx["supplier_org_id"]}
    posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Сообщение заказчика", "idempotency_key": "dual-message"},
        headers=customer_headers,
    )
    assert posted.status_code == 200, posted.text

    cross_side_replay = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Сообщение заказчика", "idempotency_key": "dual-message"},
        headers=supplier_headers,
    )
    assert cross_side_replay.status_code == 409

    supplier_posted = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Сообщение исполнителя", "idempotency_key": "dual-message-2"},
        headers=supplier_headers,
    )
    assert supplier_posted.status_code == 200, supplier_posted.text

    room = client.get(
        f"/deal-room/{ctx['booking_id']}", headers=customer_headers
    ).json()
    customer_message = next(
        message for message in room["messages"] if message["body"] == "Сообщение заказчика"
    )
    supplier_message = next(
        message for message in room["messages"] if message["body"] == "Сообщение исполнителя"
    )
    assert customer_message["author_org_id"] == ctx["customer_org_id"]
    assert customer_message["author_side"] == "customer"
    assert customer_message["author_name"] == "Клиент MSG"
    assert customer_message["actor_role"] == "owner"
    assert customer_message["attribution_status"] == "attributed"
    assert supplier_message["author_org_id"] == ctx["supplier_org_id"]
    assert supplier_message["author_side"] == "supplier"
    assert supplier_message["author_name"] == "Шоу MSG"
    assert supplier_message["actor_role"] == "manager"
    assert supplier_message["attribution_status"] == "attributed"

    conversation_id = next(
        item["conversation_id"]
        for item in client.get("/messages/inbox", headers=customer_headers).json()["items"]
        if item["booking_id"] == ctx["booking_id"]
    )
    assert client.get("/messages/inbox", headers=ctx["ch"]).status_code == 409
    assert (
        client.get(
            "/messages/inbox",
            headers={**ctx["ch"], "X-Booker-Org": "not-a-member"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/conversations/{conversation_id}/read",
            headers={**ctx["ch"], "X-Booker-Org": "not-a-party"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/conversations/{conversation_id}/read", headers=customer_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/conversations/{conversation_id}/read", headers=supplier_headers
        ).status_code
        == 200
    )

    customer_new = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Новое от заказчика", "idempotency_key": "dual-unread-customer"},
        headers=customer_headers,
    )
    assert customer_new.status_code == 200, customer_new.text
    customer_inbox = client.get("/messages/inbox", headers=customer_headers).json()["items"]
    supplier_inbox = client.get("/messages/inbox", headers=supplier_headers).json()["items"]
    customer_thread = next(i for i in customer_inbox if i["booking_id"] == ctx["booking_id"])
    supplier_thread = next(i for i in supplier_inbox if i["booking_id"] == ctx["booking_id"])
    assert customer_thread["viewer_side"] == "customer"
    assert customer_thread["unread_count"] == 0
    assert supplier_thread["viewer_side"] == "supplier"
    assert supplier_thread["unread_count"] == 1

    assert (
        client.post(
            f"/conversations/{conversation_id}/read", headers=supplier_headers
        ).status_code
        == 200
    )
    supplier_new = client.post(
        f"/deal-room/{ctx['booking_id']}/messages",
        json={"body": "Новое от исполнителя", "idempotency_key": "dual-unread-supplier"},
        headers=supplier_headers,
    )
    assert supplier_new.status_code == 200, supplier_new.text
    customer_thread = next(
        i
        for i in client.get("/messages/inbox", headers=customer_headers).json()["items"]
        if i["booking_id"] == ctx["booking_id"]
    )
    supplier_thread = next(
        i
        for i in client.get("/messages/inbox", headers=supplier_headers).json()["items"]
        if i["booking_id"] == ctx["booking_id"]
    )
    assert customer_thread["unread_count"] == 1
    assert supplier_thread["unread_count"] == 0


def test_request_conversation_survives_offer_and_enforces_acl(client, SessionLocal):
    from booker_api.models import (
        Booking,
        Conversation,
        Event,
        Message,
        Organization,
        Request,
        User,
    )

    customer = register(client, "prechat-customer@booker.test", "Клиент")
    supplier = register(client, "prechat-supplier@booker.test", "Артист")
    outsider = register(client, "prechat-outsider@booker.test", "Чужой")
    viewer = register(client, "prechat-viewer@booker.test", "Наблюдатель")
    customer_headers = auth_header(customer["token"])
    supplier_headers = auth_header(supplier["token"])
    outsider_headers = auth_header(outsider["token"])
    customer_org = client.post(
        "/orgs",
        json={"name": "Клиент до оффера", "kind": "customer"},
        headers=customer_headers,
    ).json()
    supplier_org = client.post(
        "/orgs",
        json={"name": "Артист до оффера", "kind": "artist"},
        headers=supplier_headers,
    ).json()
    outsider_org = client.post(
        "/orgs",
        json={"name": "Чужая организация", "kind": "customer"},
        headers=outsider_headers,
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": supplier_org["id"], "name": "DJ до оффера"},
        headers=supplier_headers,
    ).json()
    starts = (now() + timedelta(days=12)).replace(microsecond=0)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=2)).isoformat(),
        },
        headers=supplier_headers,
    ).json()
    publish_artist(client, supplier, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": customer_org["id"],
            "title": "Диалог до оффера",
            "event_date": starts.isoformat(),
            "requirements": [{"category_code": "dj", "qty": 1}],
        },
        headers=customer_headers,
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "requirement_id": event["requirements"][0]["id"],
        },
        headers=customer_headers,
    ).json()
    added_viewer = client.post(
        f"/orgs/{customer_org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=customer_headers,
    )
    assert added_viewer.status_code == 200

    customer_view = client.get(
        f"/requests/{req['id']}/conversation", headers=customer_headers
    )
    supplier_view = client.get(
        f"/requests/{req['id']}/conversation", headers=supplier_headers
    )
    denied = client.get(
        f"/requests/{req['id']}/conversation",
        headers=outsider_headers,
    )
    assert customer_view.status_code == 200
    assert supplier_view.status_code == 200
    assert denied.status_code == 404
    conversation_id = customer_view.json()["conversation_id"]
    assert conversation_id == supplier_view.json()["conversation_id"]
    marked = client.post(
        f"/conversations/{conversation_id}/read", headers=supplier_headers
    )
    assert marked.status_code == 200

    viewer_headers = auth_header(viewer["token"])
    assert (
        client.get(f"/requests/{req['id']}/conversation", headers=viewer_headers).status_code
        == 200
    )
    viewer_write = client.post(
        f"/requests/{req['id']}/messages",
        json={"body": "Нельзя отправить", "idempotency_key": "viewer-write"},
        headers=viewer_headers,
    )
    assert viewer_write.status_code == 403

    with SessionLocal() as db:
        admin_row = db.get(User, outsider["user_id"])
        admin_row.email_verified_at = now()
        admin_row.is_platform_admin = True
        db.commit()
    admin_without_membership = client.get(
        f"/requests/{req['id']}/conversation",
        headers=outsider_headers,
    )
    assert admin_without_membership.status_code == 404

    sent = client.post(
        f"/requests/{req['id']}/messages",
        json={"body": "Уточним технический райдер", "idempotency_key": "prechat-1"},
        headers=customer_headers,
    )
    replay = client.post(
        f"/requests/{req['id']}/messages",
        json={"body": "Уточним технический райдер", "idempotency_key": "prechat-1"},
        headers=customer_headers,
    )
    conflict = client.post(
        f"/requests/{req['id']}/messages",
        json={"body": "Другой текст", "idempotency_key": "prechat-1"},
        headers=customer_headers,
    )
    oversized = client.post(
        f"/requests/{req['id']}/messages",
        json={"body": "x" * 8001, "idempotency_key": "prechat-too-large"},
        headers=customer_headers,
    )
    assert sent.status_code == 200
    assert replay.status_code == 200 and replay.json()["idempotent"] is True
    assert conflict.status_code == 409
    assert oversized.status_code == 422

    # Delivery order, not a client or database timestamp, defines unread state.
    with SessionLocal() as db:
        delayed = db.get(Message, sent.json()["id"])
        delayed.created_at = now() - timedelta(days=1)
        db.commit()

    pre_offer_inbox = client.get("/messages/inbox", headers=supplier_headers).json()["items"]
    pre_offer = next(item for item in pre_offer_inbox if item["request_id"] == req["id"])
    assert pre_offer["booking_id"] is None
    assert pre_offer["deal_path"] is None
    assert pre_offer["can_write"] is True
    assert pre_offer["unread_count"] == 1

    viewer_inbox = client.get("/messages/inbox", headers=viewer_headers).json()["items"]
    viewer_thread = next(item for item in viewer_inbox if item["request_id"] == req["id"])
    assert viewer_thread["can_write"] is False

    with SessionLocal() as db:
        db.get(User, outsider["user_id"]).is_platform_admin = False
        db.get(Request, req["id"]).supplier_org_id = outsider_org["id"]
        db.commit()
    stolen_offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 60000, "slot_id": slot["id"]},
        headers=outsider_headers,
    )
    assert stolen_offer.status_code == 403
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 60000, "slot_id": slot["id"]},
        headers=supplier_headers,
    )
    assert offer.status_code == 200
    duplicate_offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 60000, "slot_id": slot["id"]},
        headers=supplier_headers,
    )
    assert duplicate_offer.status_code == 409
    with SessionLocal() as db:
        assert db.query(Booking).count() == 1
    after_offer = client.get(
        f"/requests/{req['id']}/conversation", headers=customer_headers
    ).json()
    assert after_offer["conversation_id"] == conversation_id
    assert after_offer["booking_id"] == offer.json()["booking_id"]
    assert any(message["body"] == "Уточним технический райдер" for message in after_offer["messages"])

    # Conversation and Deal Room ACL are historical facts. Later edits to the source
    # event/request must not transfer an existing thread to another organization.
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation.customer_org_id == customer_org["id"]
        assert conversation.supplier_org_id == supplier_org["id"]
        db.get(User, outsider["user_id"]).is_platform_admin = False
        db.get(Organization, customer_org["id"]).name = "Новое имя заказчика"
        db.get(Organization, supplier_org["id"]).name = "Новое имя исполнителя"
        db.get(Event, event["id"]).organization_id = outsider_org["id"]
        db.get(Request, req["id"]).supplier_org_id = outsider_org["id"]
        db.commit()

    # List endpoints must honor the same immutable participant snapshot as the
    # conversation and Deal Room after source ownership is edited.
    foreign_requests = client.get(
        "/requests", params={"organization_id": outsider_org["id"]}, headers=outsider_headers
    )
    foreign_bookings = client.get(
        "/bookings", params={"organization_id": outsider_org["id"]}, headers=outsider_headers
    )
    assert foreign_requests.status_code == foreign_bookings.status_code == 200
    assert req["id"] not in {item["id"] for item in foreign_requests.json()["items"]}
    assert offer.json()["booking_id"] not in {item["id"] for item in foreign_bookings.json()["items"]}
    historical_requests = client.get(
        "/requests", params={"organization_id": supplier_org["id"]}, headers=supplier_headers
    )
    historical_bookings = client.get(
        "/bookings", params={"organization_id": customer_org["id"]}, headers=customer_headers
    )
    assert req["id"] in {item["id"] for item in historical_requests.json()["items"]}
    assert offer.json()["booking_id"] in {item["id"] for item in historical_bookings.json()["items"]}
    denied_cancel = client.post(
        f"/bookings/{offer.json()['booking_id']}/cancel",
        json={"reason": "Чужая организация"},
        headers=outsider_headers,
    )
    assert denied_cancel.status_code == 403
    with SessionLocal() as db:
        assert db.get(Booking, offer.json()["booking_id"]).status != "Cancelled"

    assert (
        client.get(f"/requests/{req['id']}/conversation", headers=customer_headers).status_code
        == 200
    )
    assert (
        client.get(f"/requests/{req['id']}/conversation", headers=supplier_headers).status_code
        == 200
    )
    assert (
        client.get(f"/requests/{req['id']}/conversation", headers=outsider_headers).status_code
        == 404
    )
    stable_room = client.get(
        f"/deal-room/{offer.json()['booking_id']}", headers=customer_headers
    )
    assert stable_room.status_code == 200
    participant_names = {item["role"]: item["name"] for item in stable_room.json()["participants"]}
    assert participant_names["customer"] == "Клиент до оффера"
    assert participant_names["supplier"] == "Артист до оффера"
    assert (
        client.get(f"/deal-room/{offer.json()['booking_id']}", headers=supplier_headers).status_code
        == 200
    )
    assert (
        client.get(f"/deal-room/{offer.json()['booking_id']}", headers=outsider_headers).status_code
        == 403
    )
    stable_inbox = client.get("/messages/inbox", headers=customer_headers).json()["items"]
    stable_thread = next(item for item in stable_inbox if item["request_id"] == req["id"])
    assert stable_thread["customer_org"] == "Клиент до оффера"
    assert stable_thread["supplier_org"] == "Артист до оффера"

    outsider_version = client.post(
        f"/offers/{offer.json()['id']}/versions",
        json={"honorarium_rub": 61_000},
        headers=outsider_headers,
    )
    assert outsider_version.status_code == 403
    stable_version = client.post(
        f"/offers/{offer.json()['id']}/versions",
        json={"honorarium_rub": 61_000},
        headers=supplier_headers,
    )
    assert stable_version.status_code == 200, stable_version.text
    quote_id = stable_version.json()["quote_id"]
    assert client.post(
        f"/offers/{offer.json()['id']}/ack",
        json={"quote_id": quote_id, "side": "supplier"},
        headers=outsider_headers,
    ).status_code == 403
    assert client.post(
        f"/offers/{offer.json()['id']}/ack",
        json={"quote_id": quote_id, "side": "supplier"},
        headers=supplier_headers,
    ).status_code == 200
    assert client.post(
        f"/offers/{offer.json()['id']}/ack",
        json={"quote_id": quote_id, "side": "customer"},
        headers=customer_headers,
    ).status_code == 200
    assert client.post(
        f"/bookings/{offer.json()['booking_id']}/hold", headers=customer_headers
    ).status_code == 200
    assert client.post(
        f"/bookings/{offer.json()['booking_id']}/contract", headers=outsider_headers
    ).status_code == 403
    assert client.post(
        f"/bookings/{offer.json()['booking_id']}/contract", headers=customer_headers
    ).status_code == 200

    with SessionLocal() as db:
        db.get(Booking, offer.json()["booking_id"]).status = "Completed"
        db.commit()
    assert client.post(
        f"/bookings/{offer.json()['booking_id']}/reviews",
        json={"rating": 5, "text": "Снимок сторон сохранён"},
        headers=customer_headers,
    ).status_code == 200
    assert client.post(
        f"/bookings/{offer.json()['booking_id']}/reviews",
        json={"rating": 5, "text": "Чужой отзыв"},
        headers=outsider_headers,
    ).status_code == 403
