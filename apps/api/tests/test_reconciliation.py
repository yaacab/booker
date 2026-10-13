from datetime import timedelta

import pytest

from booker_api.models import (
    Booking,
    MoneyMovement,
    Payment,
    ReconciliationDiscrepancy,
    ReconciliationEntry,
    ReconciliationRun,
)
from booker_api.money_movements import append_money_movement
from booker_api.reconciliation import import_reconciliation_report, resolve_discrepancy
from booker_api.security import aware
from tests.conftest import auth_header
from tests.test_payments import _awaiting_payment


def _captured(client):
    ctx = _awaiting_payment(client)
    completed = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert completed.status_code == 200, completed.text
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, ctx["payment_id"])
        movement = db.query(MoneyMovement).filter_by(payment_id=payment.id, kind="capture").one()
        return ctx, {
            "payment_id": payment.id,
            "provider_reference": payment.provider_reference,
            "merchant": payment.provider_merchant,
            "amount_rub": movement.amount_rub,
            "movement_at": aware(movement.created_at),
        }


def _report_row(facts, **overrides):
    row = {
        "provider_operation_id": "provider-op-1",
        "provider_reference": facts["provider_reference"],
        "operation_kind": "capture",
        "amount_rub": facts["amount_rub"],
        "currency": "RUB",
        "provider_status": "succeeded",
        "occurred_at": facts["movement_at"].isoformat(),
    }
    row.update(overrides)
    return row


def _run(db, facts, *, report_id="report-1", entries=None, complete=True):
    return import_reconciliation_report(
        db,
        provider="stub",
        merchant=facts["merchant"],
        report_id=report_id,
        period_start=facts["movement_at"] - timedelta(hours=1),
        period_end=facts["movement_at"] + timedelta(hours=1),
        entries=[_report_row(facts)] if entries is None else entries,
        complete=complete,
    )


def test_exact_provider_capture_matches_ledger(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        result = _run(db, facts)
        db.commit()
        assert result["status"] == "completed"
        assert result["matched"] == 1
        assert result["discrepancies"] == 0
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is False


def test_missing_provider_row_blocks_payout_without_mutating_ledger(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        before = db.query(MoneyMovement).count()
        result = _run(db, facts, entries=[])
        db.commit()
        discrepancy = db.query(ReconciliationDiscrepancy).one()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)
        assert result["status"] == "completed_with_discrepancies"
        assert discrepancy.kind == "missing_at_provider"
        assert booking.payout_blocked is True
        assert booking.status == "Confirmed"
        assert db.query(MoneyMovement).count() == before

        resolve_discrepancy(
            db,
            discrepancy,
            actor_user_id=ctx_user_id(client, _ctx["customer"]["token"]),
            resolution="Проверено по независимому документу",
        )
        db.commit()
        assert booking.payout_blocked is False


def test_capture_without_provider_reference_is_discrepancy_and_blocks_payout(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        payment.provider_reference = None
        db.commit()
        result = _run(db, facts, entries=[])
        db.commit()
        assert result["status"] == "completed_with_discrepancies"
        assert result["discrepancies"] == 1
        assert db.query(ReconciliationDiscrepancy).one().kind == "provider_reference_missing"
        assert db.get(Booking, payment.booking_id).payout_blocked is True


def ctx_user_id(client, token):
    return client.get("/me", headers=auth_header(token)).json()["id"]


def test_amount_mismatch_and_unknown_partner_operation_are_reported(client):
    _ctx, facts = _captured(client)
    unknown = _report_row(
        facts,
        provider_operation_id="provider-op-unknown",
        provider_reference="stub-unknown-payment",
    )
    mismatch = _report_row(facts, amount_rub=facts["amount_rub"] + 1)
    with client.app.state.SessionLocal() as db:
        result = _run(db, facts, entries=[mismatch, unknown])
        db.commit()
        kinds = {row.kind for row in db.query(ReconciliationDiscrepancy).all()}
    assert result["discrepancies"] == 2
    assert kinds == {"amount_mismatch", "missing_in_ledger"}
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is True


def test_report_replay_is_idempotent_and_conflicting_hash_is_recorded(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        first = _run(db, facts)
        db.commit()
        replay = _run(db, facts)
        assert replay["idempotent"] is True
        conflict = _run(
            db,
            facts,
            entries=[_report_row(facts, provider_operation_id="different")],
        )
        db.commit()
        assert conflict["conflict"] is True
        assert db.query(ReconciliationEntry).count() == 1
        assert db.query(ReconciliationDiscrepancy).filter_by(kind="report_hash_conflict").count() == 1
        assert first["run_id"] == replay["run_id"] == conflict["run_id"]


def test_incomplete_report_fails_with_global_block_and_no_entries(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        result = _run(db, facts, complete=False)
        db.commit()
        assert result["status"] == "failed"
        assert db.query(ReconciliationEntry).count() == 0
        discrepancy = db.query(ReconciliationDiscrepancy).one()
        assert discrepancy.kind == "incomplete_report"
        payment = db.get(Payment, facts["payment_id"])
        assert db.get(Booking, payment.booking_id).payout_blocked is True


def test_same_content_under_another_report_id_is_idempotent(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        first = _run(db, facts, report_id="registry-a")
        db.commit()
        replay = _run(db, facts, report_id="registry-b")

    assert replay == {
        "run_id": first["run_id"],
        "status": "completed",
        "idempotent": True,
    }


def test_entry_timestamp_is_required(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        row = _report_row(facts, occurred_at=None)
        with pytest.raises(ValueError, match="occurred_at должен быть датой ISO 8601"):
            _run(db, facts, entries=[row])


def test_reconciliation_is_isolated_by_merchant(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        result = import_reconciliation_report(
            db,
            provider="stub",
            merchant="another-merchant",
            report_id="other-merchant-report",
            period_start=facts["movement_at"] - timedelta(hours=1),
            period_end=facts["movement_at"] + timedelta(hours=1),
            entries=[_report_row(facts)],
        )
        db.commit()
        discrepancy = db.query(ReconciliationDiscrepancy).one()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)

    assert result["discrepancies"] == 1
    assert discrepancy.kind == "missing_in_ledger"
    assert discrepancy.payment_id is None
    assert booking.payout_blocked is False


def test_multiple_partial_refunds_match_one_to_one(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        for index, amount in enumerate((10, 15), start=1):
            append_money_movement(
                db,
                payment=payment,
                kind="refund",
                direction="debit",
                amount_rub=amount,
                source_type="test-refund",
                source_id=f"refund-{index}",
            )
        db.commit()
        entries = [
            _report_row(facts),
            _report_row(
                facts,
                provider_operation_id="refund-op-1",
                operation_kind="refund",
                amount_rub=10,
            ),
            _report_row(
                facts,
                provider_operation_id="refund-op-2",
                operation_kind="refund",
                amount_rub=15,
            ),
        ]
        result = _run(db, facts, entries=entries)
        db.commit()

    assert result["matched"] == 3
    assert result["discrepancies"] == 0


def test_reconciliation_identity_is_immutable(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        result = _run(db, facts)
        db.commit()
        run = db.get(ReconciliationRun, result["run_id"])
        run.merchant = "changed"
        with pytest.raises(ValueError, match="Идентичность запуска сверки неизменяема"):
            db.flush()


def test_legacy_unassigned_merchant_fails_closed(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, facts["payment_id"])
        payment.provider_merchant = ""
        db.commit()
        result = import_reconciliation_report(
            db,
            provider="stub",
            merchant="stub",
            report_id="legacy-merchant-report",
            period_start=facts["movement_at"] - timedelta(hours=1),
            period_end=facts["movement_at"] + timedelta(hours=1),
            entries=[],
        )
        db.commit()
        discrepancy = db.query(ReconciliationDiscrepancy).one()
        booking = db.get(Booking, payment.booking_id)

    assert result["status"] == "completed_with_discrepancies"
    assert discrepancy.kind == "legacy_merchant_unassigned"
    assert booking.payout_blocked is True


def test_provider_operation_cannot_be_reused_in_another_report(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        first = _run(db, facts, report_id="first-registry")
        db.commit()
        second = import_reconciliation_report(
            db,
            provider="stub",
            merchant=facts["merchant"],
            report_id="second-registry",
            period_start=facts["movement_at"] - timedelta(hours=2),
            period_end=facts["movement_at"] + timedelta(hours=2),
            entries=[_report_row(facts)],
        )
        db.commit()
        kinds = {row.kind for row in db.query(ReconciliationDiscrepancy).all()}

    assert first["status"] == "completed"
    assert second["status"] == "failed"
    assert "provider_operation_reused" in kinds


def test_reconciliation_audit_rows_cannot_be_deleted(client):
    _ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        result = _run(db, facts)
        db.commit()
        run = db.get(ReconciliationRun, result["run_id"])
        db.delete(run)
        with pytest.raises(ValueError, match="Записи сверки нельзя удалять"):
            db.flush()
