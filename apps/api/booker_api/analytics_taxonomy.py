"""Pilot analytics taxonomy — client events allowlist and dashboard step keys."""

from __future__ import annotations

# Client events recorded via POST /analytics/events → audit client.event
ALLOWED_CLIENT_EVENTS: frozenset[str] = frozenset(
    {
        # Discovery & navigation
        "page.view",
        "search.performed",
        "deal.room.opened",
        # Event Studio (demand)
        "event.studio.started",
        "event.studio.completed",
        # Supply cabinet
        "cabinet.viewed",
        "cabinet.offer_sent",
        "cabinet.service_created",
        "cabinet.ical_imported",
        "cabinet.vacation_set",
    }
)

CLIENT_EVENT_GROUPS: dict[str, tuple[str, ...]] = {
    "studio": ("event.studio.started", "event.studio.completed"),
    "cabinet": (
        "cabinet.viewed",
        "cabinet.offer_sent",
        "cabinet.service_created",
        "cabinet.ical_imported",
        "cabinet.vacation_set",
    ),
    "discovery": ("page.view", "search.performed", "deal.room.opened"),
}

# Funnel steps for admin dashboards (key → audit filter)
FUNNEL_STEPS: tuple[tuple[str, str, str | None], ...] = (
    ("event.studio.started", "client.event", "event.studio.started"),
    ("event.studio.completed", "client.event", "event.studio.completed"),
    ("requirement.created", "requirement.created", None),
    ("request.created", "request.created", None),
    ("offer.created", "offer.created", None),
    ("hold.created", "hold.created", None),
    ("contract.signed", "contract.signed", None),
    ("payment.webhook", "payment.webhook", None),
)
