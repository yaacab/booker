"""Read-only booking context for a support assistant session."""

from booker_api.models import Booking
from tests.conftest import auth_header, register
from tests.test_support_agent import _create_session, _send
from tests.test_support_security import _create_org, _seed_related_graph


def test_booking_status_advice_uses_authorized_current_server_state(client, SessionLocal):
    customer = register(client, "support-booking-customer@booker.test")
    supplier = register(client, "support-booking-supplier@booker.test")
    outsider = register(client, "support-booking-outsider@booker.test")
    customer_org = _create_org(client, customer, "Booking Customer")
    supplier_org = _create_org(client, supplier, "Booking Supplier", "artist")
    graph = _seed_related_graph(SessionLocal, customer_org["id"], supplier_org["id"])

    denied = client.post(
        "/support/assistant/sessions",
        json={"related_type": "booking", "related_id": graph["booking"]},
        headers={**auth_header(outsider["token"]),
                 "Idempotency-Key": "outsider-booking-context"},
    )
    assert denied.status_code == 404

    created = client.post(
        "/support/assistant/sessions",
        json={"organization_id": customer_org["id"],
              "related_type": "booking", "related_id": graph["booking"]},
        headers={**auth_header(customer["token"]),
                 "Idempotency-Key": "customer-booking-context"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    first = _send(client, customer, session_id, "Какой статус брони?", "booking-status-1")
    assert first["intent"] == "booking_flow"
    assert "обсуждение условий" in first["assistant_message"]
    assert "support.booking_status" in first["source_ids"]
    assert "не подтверждает движение денег" in first["assistant_message"]

    with SessionLocal() as db:
        booking = db.get(Booking, graph["booking"])
        booking.status = "Confirmed"
        db.commit()
    second = _send(client, customer, session_id, "Что со статусом брони?", "booking-status-2")
    assert "подтверждено в Букере" in second["assistant_message"]
    money_question = _send(
        client, customer, session_id,
        "Оплатил, а бронь не подтверждена", "booking-money-question",
    )
    assert money_question["intent"] == "paid_not_confirmed"
    assert money_question["needs_human"] is True
    assert "support.booking_status" not in money_question["source_ids"]

    generic = _create_session(
        client, customer, customer_org["id"], "booking-generic-session",
    )
    plain = _send(client, customer, generic["id"], "Какой статус брони?", "booking-plain-1")
    assert "support.booking_status" not in plain["source_ids"]
    assert "подтверждено" not in plain["assistant_message"]
