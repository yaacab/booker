"""Provider-neutral, two-way payment reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import (
    Booking,
    MoneyMovement,
    Payment,
    ReconciliationDiscrepancy,
    ReconciliationEntry,
    ReconciliationRun,
    new_id,
)
from booker_api.notifications.outbox import enqueue_email
from booker_api.security import aware, now

VALID_KINDS = frozenset({"capture", "refund"})


def _utc(value: str | datetime | None, *, field: str) -> datetime:
    if value is None:
        raise ValueError(f"{field} должен быть датой ISO 8601")
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError(f"{field} должен быть датой ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} должен содержать часовой пояс")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint(kind: str, *parts: str | None) -> str:
    return hashlib.sha256("|".join([kind, *(part or "-" for part in parts)]).encode()).hexdigest()


def _add_discrepancy(
    db: Session,
    *,
    run: ReconciliationRun,
    kind: str,
    booking: Booking | None = None,
    payment: Payment | None = None,
    movement: MoneyMovement | None = None,
    entry: ReconciliationEntry | None = None,
    details: dict[str, Any] | None = None,
) -> ReconciliationDiscrepancy:
    fingerprint = _fingerprint(
        kind,
        payment.id if payment else None,
        movement.id if movement else None,
        entry.id if entry else None,
    )
    existing = (
        db.query(ReconciliationDiscrepancy)
        .filter_by(run_id=run.id, fingerprint=fingerprint)
        .one_or_none()
    )
    if existing:
        if existing.status == "open" or kind != "report_hash_conflict":
            return existing
        fingerprint = _fingerprint(kind, fingerprint, new_id())
    row = ReconciliationDiscrepancy(
        run_id=run.id,
        fingerprint=fingerprint,
        kind=kind,
        booking_id=booking.id if booking else None,
        payment_id=payment.id if payment else None,
        movement_id=movement.id if movement else None,
        entry_id=entry.id if entry else None,
        details_json=json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
        status="open",
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = (
            db.query(ReconciliationDiscrepancy)
            .filter_by(run_id=run.id, fingerprint=fingerprint)
            .one()
        )
    enqueue_email(
        db,
        idempotency_key=f"reconciliation:p0:{row.id}",
        recipient_email=settings.support_email,
        subject="Букер: P0 расхождение сверки платежей",
        body=(
            "Обнаружено расхождение сверки. Выплата заблокирована до ручной проверки.\n"
            f"Запуск: {run.id}\nРасхождение: {row.id}\nТип: {kind}\n"
            "Откройте закрытую очередь администратора для разбора."
        ),
        template="reconciliation_p0",
        entity_type="reconciliation",
        entity_id=row.id,
    )
    return row


def _refresh_merchant_blocks(db: Session, run: ReconciliationRun) -> None:
    booking_ids = {
        row[0]
        for row in db.query(Payment.booking_id)
        .filter_by(provider=run.provider, provider_merchant=run.merchant)
        .all()
    }
    booking_ids.update(
        row[0]
        for row in db.query(ReconciliationDiscrepancy.booking_id)
        .join(ReconciliationRun, ReconciliationRun.id == ReconciliationDiscrepancy.run_id)
        .filter(
            ReconciliationRun.provider == run.provider,
            ReconciliationRun.merchant == run.merchant,
            ReconciliationDiscrepancy.booking_id.is_not(None),
        )
        .all()
    )
    for booking_id in sorted(booking_ids):
        booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().one()
        direct_open = (
            db.query(ReconciliationDiscrepancy.id)
            .filter(
                ReconciliationDiscrepancy.status == "open",
                ReconciliationDiscrepancy.booking_id == booking_id,
            )
            .first()
            is not None
        )
        global_open = (
            db.query(ReconciliationDiscrepancy.id)
            .join(ReconciliationRun, ReconciliationRun.id == ReconciliationDiscrepancy.run_id)
            .join(Payment, Payment.booking_id == booking_id)
            .filter(
                ReconciliationDiscrepancy.status == "open",
                ReconciliationDiscrepancy.booking_id.is_(None),
                ReconciliationRun.provider == Payment.provider,
                ReconciliationRun.merchant == Payment.provider_merchant,
            )
            .first()
            is not None
        )
        has_open = direct_open or global_open
        booking.payout_blocked = has_open
        booking.payout_block_reason = "reconciliation" if has_open else ""


def import_reconciliation_report(
    db: Session,
    *,
    provider: str,
    merchant: str,
    report_id: str,
    period_start: str | datetime,
    period_end: str | datetime,
    entries: list[dict[str, Any]],
    complete: bool = True,
) -> dict[str, Any]:
    """Persist a normalized report and compare it in both directions."""
    provider = provider.strip().lower()
    merchant = merchant.strip()
    report_id = report_id.strip()
    if not provider or provider in {"external", "disabled"}:
        raise ValueError("Режим provider не участвует в партнёрской сверке")
    if not merchant or not report_id:
        raise ValueError("merchant и report_id обязательны")
    start = _utc(period_start, field="period_start")
    end = _utc(period_end, field="period_end")
    if end <= start:
        raise ValueError("period_end должен быть позже period_start")

    normalized: list[dict[str, Any]] = []
    for line_no, raw in enumerate(entries, start=1):
        kind = str(raw.get("operation_kind") or "").strip().lower()
        amount = int(raw.get("amount_rub") or 0)
        if kind not in VALID_KINDS or amount <= 0:
            raise ValueError(f"Некорректная строка реестра {line_no}")
        normalized.append(
            {
                "line_no": line_no,
                "provider_operation_id": str(raw.get("provider_operation_id") or "").strip(),
                "provider_reference": str(raw.get("provider_reference") or "").strip(),
                "operation_kind": kind,
                "amount_rub": amount,
                "currency": str(raw.get("currency") or "RUB").strip().upper(),
                "provider_status": str(raw.get("provider_status") or "").strip().lower(),
                "occurred_at": _utc(raw.get("occurred_at"), field=f"entries[{line_no}].occurred_at"),
            }
        )
        if not normalized[-1]["provider_operation_id"] or not normalized[-1]["provider_reference"]:
            raise ValueError(f"В строке {line_no} нет идентификатора операции или платежа")
        if not (start <= normalized[-1]["occurred_at"] < end):
            raise ValueError(f"Строка {line_no} находится вне периода реестра")

    hash_payload = {
        "provider": provider,
        "merchant": merchant,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "complete": complete,
        "entries": [
            {**row, "occurred_at": row["occurred_at"].isoformat()} for row in normalized
        ],
    }
    content_sha256 = _canonical_hash(hash_payload)
    existing = (
        db.query(ReconciliationRun)
        .filter_by(provider=provider, merchant=merchant, report_id=report_id)
        .one_or_none()
    )
    if existing:
        if existing.content_sha256 == content_sha256:
            return {"run_id": existing.id, "status": existing.status, "idempotent": True}
        _add_discrepancy(
            db,
            run=existing,
            kind="report_hash_conflict",
            details={"received_sha256": content_sha256, "stored_sha256": existing.content_sha256},
        )
        existing.status = "failed"
        existing.failure_reason = "report_id повторно использован с другим содержимым"
        db.flush()
        _refresh_merchant_blocks(db, existing)
        return {"run_id": existing.id, "status": existing.status, "conflict": True}

    duplicate_content = (
        db.query(ReconciliationRun)
        .filter_by(provider=provider, merchant=merchant, content_sha256=content_sha256)
        .one_or_none()
    )
    if duplicate_content:
        return {
            "run_id": duplicate_content.id,
            "status": duplicate_content.status,
            "idempotent": True,
        }

    run = ReconciliationRun(
        provider=provider,
        merchant=merchant,
        report_id=report_id,
        content_sha256=content_sha256,
        period_start=start,
        period_end=end,
        status="processing",
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        concurrent_by_id = (
            db.query(ReconciliationRun)
            .filter_by(provider=provider, merchant=merchant, report_id=report_id)
            .one_or_none()
        )
        concurrent_by_content = (
            db.query(ReconciliationRun)
            .filter_by(provider=provider, merchant=merchant, content_sha256=content_sha256)
            .one_or_none()
        )
        concurrent = concurrent_by_id or concurrent_by_content
        if concurrent is None:
            raise
        if concurrent.content_sha256 == content_sha256:
            return {"run_id": concurrent.id, "status": concurrent.status, "idempotent": True}
        _add_discrepancy(
            db,
            run=concurrent,
            kind="report_hash_conflict",
            details={"received_sha256": content_sha256, "stored_sha256": concurrent.content_sha256},
        )
        concurrent.status = "failed"
        concurrent.failure_reason = "report_id повторно использован с другим содержимым"
        db.flush()
        _refresh_merchant_blocks(db, concurrent)
        return {"run_id": concurrent.id, "status": concurrent.status, "conflict": True}
    if not complete:
        _add_discrepancy(db, run=run, kind="incomplete_report")
        run.status = "failed"
        run.failure_reason = "Реестр помечен как неполный"
        run.completed_at = now()
        db.flush()
        _refresh_merchant_blocks(db, run)
        return {"run_id": run.id, "status": run.status, "discrepancies": 1}

    operation_counts = Counter(row["provider_operation_id"] for row in normalized)
    duplicate_operations = sorted(
        operation_id for operation_id, count in operation_counts.items() if count > 1
    )
    if duplicate_operations:
        _add_discrepancy(
            db,
            run=run,
            kind="duplicate_provider_operation",
            details={"provider_operation_ids": duplicate_operations},
        )
        run.status = "failed"
        run.failure_reason = "Реестр содержит повторяющиеся операции"
        run.completed_at = now()
        db.flush()
        _refresh_merchant_blocks(db, run)
        return {"run_id": run.id, "status": run.status, "discrepancies": 1}

    prior_operation = (
        db.query(ReconciliationEntry)
        .filter(
            ReconciliationEntry.provider == provider,
            ReconciliationEntry.merchant == merchant,
            ReconciliationEntry.provider_operation_id.in_(operation_counts),
        )
        .first()
    )
    if prior_operation:
        _add_discrepancy(
            db,
            run=run,
            kind="provider_operation_reused",
            details={"provider_operation_id": prior_operation.provider_operation_id},
        )
        run.status = "failed"
        run.failure_reason = "Операция провайдера уже присутствует в другом реестре"
        run.completed_at = now()
        db.flush()
        _refresh_merchant_blocks(db, run)
        return {"run_id": run.id, "status": run.status, "discrepancies": 1}

    entry_rows: list[ReconciliationEntry] = []
    try:
        with db.begin_nested():
            for item in normalized:
                row = ReconciliationEntry(
                    run_id=run.id,
                    provider=provider,
                    merchant=merchant,
                    **item,
                )
                db.add(row)
                entry_rows.append(row)
            db.flush()
    except IntegrityError:
        reused = (
            db.query(ReconciliationEntry)
            .filter(
                ReconciliationEntry.provider == provider,
                ReconciliationEntry.merchant == merchant,
                ReconciliationEntry.provider_operation_id.in_(operation_counts),
            )
            .first()
        )
        _add_discrepancy(
            db,
            run=run,
            kind="provider_operation_reused",
            details={
                "provider_operation_id": reused.provider_operation_id if reused else "concurrent"
            },
        )
        run.status = "failed"
        run.failure_reason = "Операция провайдера конкурентно импортирована другим реестром"
        run.completed_at = now()
        db.flush()
        _refresh_merchant_blocks(db, run)
        return {"run_id": run.id, "status": run.status, "discrepancies": 1}

    movements = (
        db.query(MoneyMovement)
        .join(Payment, Payment.id == MoneyMovement.payment_id)
        .filter(
            Payment.provider == provider,
            Payment.provider_merchant == merchant,
            MoneyMovement.created_at >= start,
            MoneyMovement.created_at < end,
        )
        .order_by(MoneyMovement.created_at.asc(), MoneyMovement.id.asc())
        .all()
    )
    movements_by_key: dict[tuple[str, str], list[MoneyMovement]] = {}
    movement_payments: dict[str, Payment] = {}
    discrepancies = 0
    matched = 0
    for movement in movements:
        if not (start <= aware(movement.created_at) < end):
            continue
        payment = db.get(Payment, movement.payment_id)
        if not payment:
            continue
        if not payment.provider_reference:
            _add_discrepancy(
                db,
                run=run,
                kind="provider_reference_missing",
                booking=db.get(Booking, movement.booking_id),
                payment=payment,
                movement=movement,
            )
            discrepancies += 1
            continue
        movement_payments[movement.id] = payment
        movements_by_key.setdefault((payment.provider_reference, movement.kind), []).append(movement)
    legacy_movements = (
        db.query(MoneyMovement)
        .join(Payment, Payment.id == MoneyMovement.payment_id)
        .filter(
            Payment.provider == provider,
            Payment.provider_merchant == "",
            MoneyMovement.created_at >= start,
            MoneyMovement.created_at < end,
        )
        .order_by(MoneyMovement.created_at.asc(), MoneyMovement.id.asc())
        .all()
    )
    for movement in legacy_movements:
        if not (start <= aware(movement.created_at) < end):
            continue
        payment = db.get(Payment, movement.payment_id)
        booking = db.get(Booking, movement.booking_id)
        _add_discrepancy(
            db,
            run=run,
            kind="legacy_merchant_unassigned",
            booking=booking,
            payment=payment,
            movement=movement,
        )
        discrepancies += 1
    consumed_movement_ids: set[str] = set()
    for entry in entry_rows:
        payment = (
            db.query(Payment)
            .filter_by(
                provider=provider,
                provider_merchant=merchant,
                provider_reference=entry.provider_reference,
            )
            .one_or_none()
        )
        booking = db.get(Booking, payment.booking_id) if payment else None
        if not payment:
            _add_discrepancy(db, run=run, kind="missing_in_ledger", entry=entry)
            discrepancies += 1
            continue
        candidates = [
            movement
            for movement in movements_by_key.get(
                (entry.provider_reference, entry.operation_kind), []
            )
            if movement.id not in consumed_movement_ids
        ]
        movement = next(
            (
                candidate
                for candidate in candidates
                if candidate.amount_rub == entry.amount_rub
                and candidate.currency == entry.currency
            ),
            candidates[0] if candidates else None,
        )
        if not movement:
            _add_discrepancy(
                db,
                run=run,
                kind="missing_in_ledger",
                booking=booking,
                payment=payment,
                entry=entry,
            )
            discrepancies += 1
            continue
        consumed_movement_ids.add(movement.id)
        mismatch = None
        if movement.amount_rub != entry.amount_rub:
            mismatch = "amount_mismatch"
        elif movement.currency != entry.currency:
            mismatch = "currency_mismatch"
        elif entry.provider_status != "succeeded":
            mismatch = "status_mismatch"
        if mismatch:
            _add_discrepancy(
                db,
                run=run,
                kind=mismatch,
                booking=booking,
                payment=payment,
                movement=movement,
                entry=entry,
            )
            discrepancies += 1
        else:
            matched += 1

    for movement in movements:
        if movement.id not in movement_payments or movement.id in consumed_movement_ids:
            continue
        payment = movement_payments[movement.id]
        booking = db.get(Booking, movement.booking_id)
        _add_discrepancy(
            db,
            run=run,
            kind="missing_at_provider",
            booking=booking,
            payment=payment,
            movement=movement,
        )
        discrepancies += 1

    run.status = "completed_with_discrepancies" if discrepancies else "completed"
    run.completed_at = now()
    db.flush()
    _refresh_merchant_blocks(db, run)
    return {
        "run_id": run.id,
        "status": run.status,
        "matched": matched,
        "discrepancies": discrepancies,
        "idempotent": False,
    }


def resolve_discrepancy(
    db: Session,
    discrepancy: ReconciliationDiscrepancy,
    *,
    actor_user_id: str,
    resolution: str,
) -> ReconciliationDiscrepancy:
    if discrepancy.status == "resolved":
        return discrepancy
    if not resolution.strip():
        raise ValueError("Решение по расхождению обязательно")
    discrepancy.status = "resolved"
    discrepancy.resolution = resolution.strip()
    discrepancy.resolved_by_user_id = actor_user_id
    discrepancy.resolved_at = now()
    db.flush()
    run = db.get(ReconciliationRun, discrepancy.run_id)
    if run:
        _refresh_merchant_blocks(db, run)
    return discrepancy
