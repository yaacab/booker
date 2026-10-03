from datetime import datetime, timezone

from booker_api.support_sla import support_acceptance_due_at


def test_acceptance_uses_working_minutes_across_close_and_weekend():
    # Friday 21:59 Moscow -> Saturday 10:14 Moscow, daily coverage.
    at = datetime(2026, 10, 2, 18, 59, tzinfo=timezone.utc)
    assert support_acceptance_due_at("urgent", started_at=at) == datetime(
        2026, 10, 3, 7, 14, tzinfo=timezone.utc
    )
    assert support_acceptance_due_at("high", started_at=at) == datetime(
        2026, 10, 3, 7, 14, tzinfo=timezone.utc
    )
    assert support_acceptance_due_at("normal", started_at=at) is None


def test_acceptance_starts_at_open_when_created_overnight():
    at = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)
    assert support_acceptance_due_at("urgent", started_at=at) == datetime(
        2026, 10, 3, 7, 15, tzinfo=timezone.utc
    )
