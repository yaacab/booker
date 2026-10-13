"""Scoped maintenance for historical support text; never print stored content."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from booker_api.db import SessionLocal
from booker_api.models import (
    Organization,
    SupportAgentExchange,
    SupportAgentFeedback,
    SupportAgentSession,
    SupportMessage,
    SupportOperatorNote,
    SupportTicket,
    User,
)
from booker_api.routers.trust import _fingerprint
from booker_api.support_agent import redact_sensitive_support_text


def sanitize_support_scope(
    db: Session,
    *,
    organization_id: str | None = None,
    unscoped_user_id: str | None = None,
    apply: bool = False,
    expected_changes: int | None = None,
    expected_plan_token: str | None = None,
    plan_key: bytes | None = None,
) -> dict:
    """Plan or apply a single tenant's allowlisted content scrub in one transaction."""
    if bool(organization_id) == bool(unscoped_user_id):
        raise ValueError("exactly one tenant scope is required")
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError("a fresh session is required")
    if not plan_key or len(plan_key) < 32:
        raise ValueError("a 32-byte plan key is required")
    if apply and (expected_changes is None or expected_changes < 0):
        raise ValueError("expected_changes is required for apply")
    if apply and not expected_plan_token:
        raise ValueError("expected_plan_token is required for apply")
    if not apply and (expected_changes is not None or expected_plan_token is not None):
        raise ValueError("apply expectations are only valid for apply")

    dialect = db.get_bind().dialect.name
    if apply and dialect == "sqlite" and not db.in_transaction():
        db.execute(text("BEGIN IMMEDIATE"))
    scope_kind = "organization" if organization_id else "unscoped_user"
    if organization_id:
        if db.get(Organization, organization_id) is None:
            raise ValueError("tenant scope does not exist")
        tickets_query = db.query(SupportTicket).filter(SupportTicket.organization_id == organization_id)
        sessions_query = db.query(SupportAgentSession).filter(
            SupportAgentSession.organization_id == organization_id
        )
    else:
        if db.get(User, unscoped_user_id) is None:
            raise ValueError("tenant scope does not exist")
        tickets_query = db.query(SupportTicket).filter(
            SupportTicket.organization_id.is_(None),
            SupportTicket.author_user_id == unscoped_user_id,
        )
        sessions_query = db.query(SupportAgentSession).filter(
            SupportAgentSession.organization_id.is_(None),
            SupportAgentSession.user_id == unscoped_user_id,
        )
    if apply and dialect == "postgresql":
        tickets_query = tickets_query.with_for_update()
        sessions_query = sessions_query.with_for_update()
    tickets = tickets_query.order_by(SupportTicket.id).all()
    sessions = sessions_query.order_by(SupportAgentSession.id).all()
    ticket_ids = {row.id for row in tickets}
    session_ids = {row.id for row in sessions}
    if any(row.ticket_id and row.ticket_id not in ticket_ids for row in sessions):
        raise ValueError("support links cross tenant scope")
    if ticket_ids:
        linked = db.query(SupportAgentSession).filter(
            SupportAgentSession.ticket_id.in_(ticket_ids)
        ).all()
        if any(row.id not in session_ids for row in linked):
            raise ValueError("support links cross tenant scope")
    escalated_ticket_ids = {row.ticket_id for row in sessions if row.ticket_id}

    def scoped_rows(model, relation, ids):
        if not ids:
            return []
        query = db.query(model).filter(relation.in_(ids)).order_by(model.id)
        if apply and dialect == "postgresql":
            query = query.with_for_update()
        return query.all()

    messages = scoped_rows(SupportMessage, SupportMessage.ticket_id, ticket_ids)
    notes = scoped_rows(SupportOperatorNote, SupportOperatorNote.ticket_id, ticket_ids)
    exchanges = scoped_rows(SupportAgentExchange, SupportAgentExchange.session_id, session_ids)
    exchange_ids = {row.id for row in exchanges}
    feedback = scoped_rows(SupportAgentFeedback, SupportAgentFeedback.exchange_id, exchange_ids)
    session_owner_by_id = {row.id: row.user_id for row in sessions}
    exchange_owner_by_id = {
        row.id: session_owner_by_id[row.session_id] for row in exchanges
    }
    if any(row.user_id != exchange_owner_by_id[row.exchange_id] for row in feedback):
        raise ValueError("support feedback crosses tenant scope")
    initial_message_by_ticket = {}
    for row in messages:
        previous = initial_message_by_ticket.get(row.ticket_id)
        if previous is None or (row.created_at, row.id) < (previous.created_at, previous.id):
            initial_message_by_ticket[row.ticket_id] = row
    copy_mismatches = sum(
        redact_sensitive_support_text(row.body)
        != redact_sensitive_support_text(initial_message_by_ticket[row.id].body)
        for row in tickets
        if row.id in initial_message_by_ticket
    )

    changes: list[tuple[object, str, str | None]] = []
    changed_rows: dict[str, set[str]] = defaultdict(set)
    table_counts: dict[str, int] = {}

    def plan(row, field: str, safe_value: str | None) -> None:
        if getattr(row, field) != safe_value:
            changes.append((row, field, safe_value))
            changed_rows[row.__tablename__].add(row.id)

    for row in tickets:
        subject = redact_sensitive_support_text(row.subject)
        body = redact_sensitive_support_text(row.body)
        plan(row, "subject", subject)
        plan(row, "body", body)
        if row.id in escalated_ticket_ids:
            # Escalation reason is not recoverable from a digest; this nullable
            # fingerprint is not consulted by the escalation replay path.
            plan(row, "request_fingerprint", None)
        elif row.idempotency_key_hash:
            plan(row, "request_fingerprint", _fingerprint({
                "organization_id": row.organization_id,
                "category": row.category,
                "subject": subject,
                "body": body,
                "related_type": row.related_type,
                "related_id": row.related_id,
            }))
    for row in messages:
        body = redact_sensitive_support_text(row.body)
        plan(row, "body", body)
        plan(row, "request_fingerprint", _fingerprint({
            "body": body, "author_kind": row.author_kind,
        }))
    for row in notes:
        body = redact_sensitive_support_text(row.body)
        plan(row, "body", body)
        plan(row, "request_fingerprint", _fingerprint({"body": body}))
    for row in exchanges:
        user_message = redact_sensitive_support_text(row.user_message)
        plan(row, "user_message", user_message)
        plan(row, "assistant_message", redact_sensitive_support_text(row.assistant_message))
        plan(row, "request_fingerprint", _fingerprint({"message": user_message}))
    for row in feedback:
        plan(row, "comment", redact_sensitive_support_text(row.comment))

    for table, ids in changed_rows.items():
        table_counts[table] = len(ids)
    digest = hmac.new(plan_key, digestmod=hashlib.sha256)
    for row, field, safe_value in sorted(
        changes, key=lambda change: (change[0].__tablename__, change[0].id, change[1])
    ):
        item = json.dumps(
            [row.__tablename__, row.id, field, getattr(row, field), safe_value],
            ensure_ascii=False, separators=(",", ":"),
        ).encode()
        digest.update(len(item).to_bytes(8, "big"))
        digest.update(item)
    plan_token = digest.hexdigest()
    report = {
        "format_version": 1,
        "scope_kind": scope_kind,
        "applied": apply,
        "scanned_rows": len(tickets) + len(sessions) + len(messages) + len(notes) + len(exchanges) + len(feedback),
        "ticket_initial_message_pairs": len(initial_message_by_ticket),
        "escalation_copies": len(escalated_ticket_ids),
        "copy_mismatches_after_sanitization": copy_mismatches,
        "plan_token": plan_token,
        "changed_rows": sum(table_counts.values()),
        "changed_fields": len(changes),
        "tables": dict(sorted(table_counts.items())),
    }
    if apply:
        if (
            len(changes) != expected_changes
            or not hmac.compare_digest(plan_token, expected_plan_token)
            or copy_mismatches
        ):
            db.rollback()
            raise ValueError("reviewed plan does not match current scope")
        try:
            for row, field, safe_value in changes:
                setattr(row, field, safe_value)
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        db.rollback()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scoped support secret dry-run/backfill")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--organization-id")
    scope.add_argument("--unscoped-user-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-changes", type=int)
    parser.add_argument("--plan-token")
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            report = sanitize_support_scope(
                db,
                organization_id=args.organization_id,
                unscoped_user_id=args.unscoped_user_id,
                apply=args.apply,
                expected_changes=args.expected_changes,
                expected_plan_token=args.plan_token,
                plan_key=os.environ.get("BOOKER_SUPPORT_BACKFILL_PLAN_KEY", "").encode(),
            )
    except (ValueError, SQLAlchemyError, OSError):
        # SQLAlchemy exceptions can include bind parameters and stored text.
        print("support secret backfill failed; no content printed", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
