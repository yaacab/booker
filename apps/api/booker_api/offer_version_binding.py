"""Recover a booking's accepted quote only when existing evidence is unambiguous."""

import re

from sqlalchemy import text

_CONTRACT_QUOTE = re.compile(r"(?:^|\n)quote_id=([0-9a-fA-F-]{36})(?:\n|$)")


def backfill_accepted_offer_versions(connection) -> int:
    rows = connection.execute(
        text("SELECT id, offer_id FROM bookings WHERE accepted_offer_version_id IS NULL")
    ).mappings().all()
    updated = 0
    for booking in rows:
        contracts = connection.execute(
            text("SELECT body FROM contracts WHERE booking_id = :booking_id"),
            {"booking_id": booking["id"]},
        ).scalars().all()
        if len(contracts) > 1:
            continue
        if contracts:
            match = _CONTRACT_QUOTE.search(contracts[0] or "")
            if not match:
                continue
            version_id = match.group(1)
        else:
            version_id = connection.execute(
                text("SELECT active_version_id FROM offers WHERE id = :offer_id"),
                {"offer_id": booking["offer_id"]},
            ).scalar_one_or_none()
        if not version_id:
            continue
        version = connection.execute(
            text(
                "SELECT offer_id, customer_ack, supplier_ack "
                "FROM offer_versions WHERE id = :version_id"
            ),
            {"version_id": version_id},
        ).mappings().one_or_none()
        if not version or version["offer_id"] != booking["offer_id"]:
            continue
        if not (version["customer_ack"] and version["supplier_ack"]):
            continue
        result = connection.execute(
            text(
                "UPDATE bookings SET accepted_offer_version_id = :version_id "
                "WHERE id = :booking_id AND accepted_offer_version_id IS NULL"
            ),
            {"version_id": version_id, "booking_id": booking["id"]},
        )
        updated += result.rowcount
    return updated
