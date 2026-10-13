"""Opt-in real PostgreSQL checks; never use the SQLite test engine as proof."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from booker_api import contract_ack
from booker_api.db import get_db
from booker_api.legal_registry import seed_draft_versions
from booker_api.main import app
from booker_api.models import (
    AvailabilitySlot,
    Booking,
    Contract,
    ContractSignature,
    Event,
    Offer,
    Organization,
    Payment,
    ReconciliationDiscrepancy,
    ReconciliationEntry,
    ReconciliationRun,
    Request,
    User,
)
from booker_api.reconciliation import import_reconciliation_report
from booker_api.routers import deals, payments
from booker_api.schemas import SignIn
from tests.conftest import auth_header, contract_otps
from tests.postgres_harness import isolated_postgres_schema
from tests.test_offers import ack_both, setup_negotiation

pytestmark = pytest.mark.postgres_integration


@pytest.fixture()
def postgres_schema():
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: real PostgreSQL integration not run")
    with isolated_postgres_schema(dsn) as resources:
        yield resources


def _seed_existing_support(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,"
            "totp_enabled,created_at) VALUES ('pg-user','pg-user@booker.test','PG User','x',"
            "false,false,CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO support_tickets (id,author_user_id,category,subject,body,status,"
            "priority,state_version,created_at) VALUES "
            "('pg-ticket','pg-user','other','Existing ticket','Existing body','open',"
            "'normal',0,CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO support_messages (id,ticket_id,author_user_id,author_kind,body,"
            "idempotency_key_hash,request_fingerprint,created_at) VALUES "
            "('pg-message','pg-ticket','pg-user','user','Existing reply','m-key','m-fp',"
            "CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO support_operator_notes (id,ticket_id,author_user_id,body,"
            "idempotency_key_hash,request_fingerprint,created_at) VALUES "
            "('pg-note','pg-ticket','pg-user','Existing note','n-key','n-fp',"
            "CURRENT_TIMESTAMP)"
        ))


def _seed_two_payment_bookings(engine):
    """Create two lockable bookings with the same provider and merchant."""
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        customer = Organization(name="PG Customer", kind="customer", city="Москва")
        supplier = Organization(name="PG Supplier", kind="artist", city="Москва")
        db.add_all([customer, supplier])
        db.flush()
        event = Event(
            organization_id=customer.id, title="PG test", city="Москва",
            event_date=now + timedelta(days=2), guest_count=20, notes="", status="Draft",
        )
        db.add(event)
        db.flush()
        for index in range(2):
            slot = AvailabilitySlot(
                resource_type="artist", resource_id=f"pg-resource-{index}",
                starts_at=now + timedelta(days=2), ends_at=now + timedelta(days=2, hours=1),
                status="open", buffer_before_min=0, buffer_after_min=0,
            )
            request = Request(
                event_id=event.id, resource_type="artist", resource_id=slot.resource_id,
                supplier_org_id=supplier.id, status="RequestSent",
            )
            db.add_all([slot, request])
            db.flush()
            offer = Offer(request_id=request.id)
            db.add(offer)
            db.flush()
            booking = Booking(
                event_id=event.id, offer_id=offer.id, slot_id=slot.id,
                status="Confirmed", payout_pending=False, payout_blocked=False,
                payout_block_reason="",
            )
            db.add(booking)
            db.flush()
            db.add(Payment(
                booking_id=booking.id, amount_rub=100, status="succeeded",
                provider="stub", provider_merchant="pg-test-merchant",
                provider_reference=f"pg-reference-{index}",
                idempotency_key=f"pg-payment-{index}",
            ))
        db.commit()


def test_postgres_migration_roundtrip_preserves_nonempty_support_and_triggers(postgres_schema):
    engine, config, _schema = postgres_schema
    command.upgrade(config, "f38f901ab2c3")
    _seed_existing_support(engine)
    command.upgrade(config, "f49a012bc3d4")
    assert "reconciliation_entries" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO reconciliation_runs (id,provider,merchant,report_id,content_sha256,"
            "period_start,period_end,status,failure_reason,received_at) VALUES "
            "('pg-run','stub','test','report','hash',CURRENT_TIMESTAMP,"
            "CURRENT_TIMESTAMP,'completed','',CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO reconciliation_entries (id,run_id,provider,merchant,line_no,"
            "provider_operation_id,provider_reference,operation_kind,amount_rub,currency,"
            "provider_status,occurred_at,created_at) VALUES "
            "('pg-entry','pg-run','stub','test',1,'op','reference','capture',100,'RUB',"
            "'succeeded',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO reconciliation_discrepancies "
            "(id,run_id,fingerprint,kind,details_json,status,resolution,created_at) VALUES "
            "('pg-discrepancy','pg-run','fp','unknown_provider_operation','{}','open','',"
            "CURRENT_TIMESTAMP)"
        ))
    for sql in (
        "UPDATE reconciliation_entries SET amount_rub=101 WHERE id='pg-entry'",
        "DELETE FROM reconciliation_entries WHERE id='pg-entry'",
        "UPDATE reconciliation_runs SET report_id='changed' WHERE id='pg-run'",
        "DELETE FROM reconciliation_runs WHERE id='pg-run'",
        "UPDATE reconciliation_discrepancies SET kind='changed' WHERE id='pg-discrepancy'",
        "DELETE FROM reconciliation_discrepancies WHERE id='pg-discrepancy'",
    ):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(sql))
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE reconciliation_discrepancies SET status='resolved',resolution='checked' "
            "WHERE id='pg-discrepancy'"
        ))
    command.downgrade(config, "f38f901ab2c3")
    assert "reconciliation_entries" not in inspect(engine).get_table_names()
    command.upgrade(config, "f49a012bc3d4")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        for table, row_id in (
            ("support_tickets", "pg-ticket"),
            ("support_messages", "pg-message"),
            ("support_operator_notes", "pg-note"),
        ):
            assert connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE id=:id"), {"id": row_id}
            ).scalar_one() == 1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "f49a012bc3d4"
        )
    support_uniques = {
        frozenset(item.get("column_names") or [])
        for item in inspect(engine).get_unique_constraints("support_messages")
    }
    assert frozenset({"ticket_id", "author_user_id", "idempotency_key_hash"}) in support_uniques


def test_postgres_duplicate_provider_reference_blocks_upgrade(postgres_schema):
    engine, config, _schema = postgres_schema
    command.upgrade(config, "head")
    _seed_two_payment_bookings(engine)
    command.downgrade(config, "f38f901ab2c3")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE payments ADD COLUMN provider_reference varchar(128)"))
        connection.execute(text(
            "ALTER TABLE payments ADD COLUMN provider_merchant varchar(128) NOT NULL DEFAULT ''"
        ))
        connection.execute(text(
            "UPDATE payments SET provider_reference='duplicate',provider_merchant='same'"
        ))
    with pytest.raises(DBAPIError):
        command.upgrade(config, "f49a012bc3d4")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "f38f901ab2c3"
        )
        assert connection.execute(text(
            "SELECT count(*) FROM payments WHERE provider_reference='duplicate'"
        )).scalar_one() == 2


def test_postgres_preexisting_reconciliation_tables_fail_closed(postgres_schema):
    engine, config, _schema = postgres_schema
    command.upgrade(config, "f38f901ab2c3")
    ReconciliationRun.__table__.create(engine)
    with pytest.raises(RuntimeError, match="Partial reconciliation schema"):
        command.upgrade(config, "f49a012bc3d4")
    ReconciliationEntry.__table__.create(engine)
    ReconciliationDiscrepancy.__table__.create(engine)
    with pytest.raises(RuntimeError, match="trigger verification"):
        command.upgrade(config, "f49a012bc3d4")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "f38f901ab2c3"
        )


def test_postgres_concurrent_reconciliation_import_and_support_cas(postgres_schema):
    engine, config, _schema = postgres_schema
    command.upgrade(config, "head")
    _seed_existing_support(engine)
    _seed_two_payment_bookings(engine)
    with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
        db.execute(text(
            "UPDATE payments SET provider_reference='pg-reference-0' "
            "WHERE provider_reference='pg-reference-1'"
        ))
    barrier = Barrier(2)
    current = datetime.now(timezone.utc)

    def import_once():
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=10)
            result = import_reconciliation_report(
                db, provider="stub", merchant="pg-test-merchant", report_id="same-report",
                period_start=current - timedelta(hours=1),
                period_end=current + timedelta(hours=1), entries=[],
            )
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: import_once(), range(2)))
    assert results[0]["run_id"] == results[1]["run_id"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM reconciliation_runs")).scalar_one() == 1

    # Two distinct imports traverse the same booking set; sorted row locks must avoid a cycle.
    barrier = Barrier(2)

    def import_distinct(index):
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=10)
            result = import_reconciliation_report(
                db, provider="stub", merchant="pg-test-merchant",
                report_id=f"different-report-{index}",
                period_start=current - timedelta(hours=1),
                period_end=current + timedelta(hours=1 + index), entries=[],
            )
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        distinct = list(pool.map(import_distinct, range(2)))
    assert distinct[0]["run_id"] != distinct[1]["run_id"]

    barrier = Barrier(2)

    def close_once():
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=10)
            return connection.execute(text(
                "UPDATE support_tickets SET state_version=state_version+1,status='closed' "
                "WHERE id='pg-ticket' AND state_version=0"
            )).rowcount

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _index: close_once(), range(2))) == [0, 1]


def test_postgres_concurrent_opposite_contract_acknowledgements_transition_booking(
    postgres_schema, monkeypatch
):
    """The second waiter must reload the first side after acquiring the shared offer lock."""
    engine, config, _schema = postgres_schema
    command.upgrade(config, "head")
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    with SessionLocal() as db:
        seed_draft_versions(db)
        db.commit()

    captured_codes: dict[str, str] = {}
    original_challenge = contract_ack.new_challenge

    def capture_challenge():
        code, digest, expires_at = original_challenge()
        captured_codes[digest] = code
        return code, digest, expires_at

    monkeypatch.setattr(payments, "new_challenge", capture_challenge)
    SessionLocal._issued_contract_codes = captured_codes

    def override_db():
        with SessionLocal() as db:
            yield db

    previous_session_factory = getattr(app.state, "SessionLocal", None)
    app.dependency_overrides[get_db] = override_db
    app.state.SessionLocal = SessionLocal
    try:
        with TestClient(app) as client:
            ctx = setup_negotiation(client)
            ack_both(client, ctx)
            customer_headers = auth_header(ctx["customer"]["token"])
            held = client.post(
                f"/bookings/{ctx['booking_id']}/hold", headers=customer_headers
            )
            assert held.status_code == 200, held.text
            freeze_barrier = Barrier(2)

            def mutate_requirements_while_issue_waits() -> int:
                with SessionLocal() as mutation_db:
                    mutation_db.execute(text("SET LOCAL lock_timeout = '5s'"))
                    actor = mutation_db.get(User, ctx["customer"]["user_id"])
                    assert actor is not None
                    freeze_barrier.wait(timeout=10)
                    try:
                        deals.put_event_requirements(
                            ctx["event"]["id"],
                            {"items": [{
                                "id": ctx["event"]["requirements"][0]["id"],
                                "category_code": "dj",
                                "qty": 2,
                                "required": True,
                                "notes": "concurrent stale mutation",
                            }]},
                            user=actor,
                            db=mutation_db,
                        )
                    except HTTPException as exc:
                        return exc.status_code
                    return 200

            with SessionLocal() as issue_db:
                issue_db.execute(text("SET LOCAL lock_timeout = '5s'"))
                issue_db.query(Event).filter(
                    Event.id == ctx["event"]["id"]
                ).with_for_update().one()
                actor = issue_db.get(User, ctx["customer"]["user_id"])
                assert actor is not None
                with ThreadPoolExecutor(max_workers=1) as pool:
                    mutation = pool.submit(mutate_requirements_while_issue_waits)
                    freeze_barrier.wait(timeout=10)
                    contract_payload = payments.create_contract(
                        ctx["booking_id"], user=actor, db=issue_db
                    )
                    assert mutation.result(timeout=10) == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        if previous_session_factory is None:
            delattr(app.state, "SessionLocal")
        else:
            app.state.SessionLocal = previous_session_factory

    codes = contract_otps(SessionLocal, contract_payload["id"])
    barrier = Barrier(2)

    def acknowledge(actor_user_id: str, organization_id: str, side: str, otp: str):
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            actor = db.get(User, actor_user_id)
            assert actor is not None
            barrier.wait(timeout=10)
            return payments.sign_contract(
                contract_payload["id"],
                SignIn(side=side, otp=otp, body_hash=contract_payload["body_sha256"]),
                user=actor,
                db=db,
                x_booker_org=organization_id,
            )

    calls = (
        (
            ctx["customer"]["user_id"],
            ctx["cust_org"]["id"],
            "customer",
            codes["otp_customer"],
        ),
        (
            ctx["owner"]["user_id"],
            ctx["artist_org"]["id"],
            "supplier",
            codes["otp_supplier"],
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: acknowledge(*args), calls))

    assert all(result["customer_signed"] or result["supplier_signed"] for result in results)
    with SessionLocal() as db:
        contract = db.get(Contract, contract_payload["id"])
        booking = db.get(Booking, ctx["booking_id"])
        signatures = (
            db.query(ContractSignature)
            .filter_by(contract_id=contract_payload["id"])
            .all()
        )
        assert contract is not None
        assert contract.customer_signed is True
        assert contract.supplier_signed is True
        assert booking is not None and booking.status == "AwaitingPayment"
        assert {signature.side for signature in signatures} == {"customer", "supplier"}
