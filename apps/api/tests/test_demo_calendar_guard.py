from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from booker_api.demo_calendar import ensure_demo_day


def test_disabled_calendar_never_touches_database(monkeypatch):
    monkeypatch.delenv("BOOKER_DEMO_OPEN_CALENDAR", raising=False)
    db = Mock()
    ensure_demo_day(db, datetime.now(timezone.utc))
    db.get_bind.assert_not_called()


def test_calendar_rejects_non_demo_database(monkeypatch):
    monkeypatch.setenv("BOOKER_DEMO_OPEN_CALENDAR", "1")
    with Session(create_engine("sqlite://")) as db:
        with pytest.raises(RuntimeError, match="isolated"):
            ensure_demo_day(db, datetime.now(timezone.utc))
