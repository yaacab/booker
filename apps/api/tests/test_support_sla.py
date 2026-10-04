import json
from datetime import datetime, timezone

import pytest

from booker_api.config import Settings, settings
from booker_api.support_sla import support_response_due_at


def test_support_deadline_is_hidden_without_approved_calendar(monkeypatch):
    monkeypatch.setattr(settings, "support_sla_schedule_json", "")
    started = datetime(2026, 10, 1, 18, 50, tzinfo=timezone.utc)
    assert support_response_due_at("event_day_no_show", 30, started_at=started) is None


def test_approved_daily_moscow_window_carries_due_time_across_22_and_weekend():
    # Friday 21:50 MSK + 30 working minutes -> Saturday 10:20 MSK.
    started = datetime(2026, 10, 2, 18, 50, tzinfo=timezone.utc)
    assert support_response_due_at("event_day_no_show", 30, started_at=started) == datetime(
        2026, 10, 3, 7, 20, tzinfo=timezone.utc
    )
    # Saturday 08:00 MSK + 2 working hours -> Saturday 12:00 MSK.
    early = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
    assert support_response_due_at("paid_not_confirmed", 120, started_at=early) == datetime(
        2026, 10, 3, 9, 0, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("local_hour", "local_minute", "due_day", "due_hour", "due_minute"),
    [(9, 59, 3, 10, 30), (10, 0, 3, 10, 30),
     (21, 59, 4, 10, 29), (22, 0, 4, 10, 30)],
)
def test_daily_moscow_boundaries_on_weekend(
    local_hour, local_minute, due_day, due_hour, due_minute
):
    started = datetime(2026, 10, 3, local_hour - 3, local_minute, tzinfo=timezone.utc)
    expected = datetime(2026, 10, due_day, due_hour - 3, due_minute, tzinfo=timezone.utc)
    assert support_response_due_at("event_day_no_show", 30, started_at=started) == expected


def test_daily_calendar_includes_holiday_and_unknown_category_has_no_deadline():
    started = datetime(2027, 1, 1, 7, 0, tzinfo=timezone.utc)
    assert support_response_due_at("paid_not_confirmed", 120, started_at=started) == datetime(
        2027, 1, 1, 9, 0, tzinfo=timezone.utc
    )
    assert support_response_due_at("other", 30, started_at=started) is None


def test_explicit_empty_environment_override_hides_deadline(monkeypatch):
    monkeypatch.setenv("BOOKER_SUPPORT_SLA_SCHEDULE_JSON", "")
    override = Settings(_env_file=None)
    assert override.support_sla_schedule_json == ""
    monkeypatch.setattr(settings, "support_sla_schedule_json", override.support_sla_schedule_json)
    assert support_response_due_at(
        "event_day_no_show", 30,
        started_at=datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc),
    ) is None


def test_support_deadline_carries_remaining_time_across_weekend_and_closed_day(monkeypatch):
    monkeypatch.setattr(
        settings,
        "support_sla_schedule_json",
        json.dumps(
            {
                "event_day_no_show": {
                    "timezone": "Europe/Moscow",
                    "weekdays": [0, 1, 2, 3, 4],
                    "start": "10:00",
                    "end": "22:00",
                    "closed_dates": ["2026-10-02"],
                }
            }
        ),
    )
    started = datetime(2026, 10, 1, 18, 50, tzinfo=timezone.utc)
    due = support_response_due_at("event_day_no_show", 30, started_at=started)
    assert due == datetime(2026, 10, 5, 7, 20, tzinfo=timezone.utc)


def test_support_deadline_uses_configured_zone_after_dst_weekend(monkeypatch):
    monkeypatch.setattr(
        settings,
        "support_sla_schedule_json",
        json.dumps(
            {
                "paid_not_confirmed": {
                    "timezone": "Europe/Berlin",
                    "weekdays": [0, 1, 2, 3, 4],
                    "start": "10:00",
                    "end": "18:00",
                    "closed_dates": [],
                }
            }
        ),
    )
    started = datetime(2026, 3, 27, 16, 30, tzinfo=timezone.utc)
    due = support_response_due_at("paid_not_confirmed", 120, started_at=started)
    assert due == datetime(2026, 3, 30, 9, 30, tzinfo=timezone.utc)


def test_incomplete_calendar_does_not_publish_a_deadline(monkeypatch):
    monkeypatch.setattr(
        settings,
        "support_sla_schedule_json",
        json.dumps({"event_day_no_show": {"timezone": "Europe/Moscow"}}),
    )
    assert (
        support_response_due_at(
            "event_day_no_show",
            30,
            started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        is None
    )


def test_nonlocal_or_ambiguous_hours_do_not_publish_a_deadline(monkeypatch):
    started = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)
    for start, end in (("10", "18:00"), ("10:00+03:00", "18:00"), ("01:00", "04:00")):
        monkeypatch.setattr(
            settings,
            "support_sla_schedule_json",
            json.dumps(
                {
                    "event_day_no_show": {
                        "timezone": "Europe/Berlin",
                        "weekdays": [6],
                        "start": start,
                        "end": end,
                        "closed_dates": [],
                    }
                }
            ),
        )
        assert support_response_due_at("event_day_no_show", 30, started_at=started) is None
