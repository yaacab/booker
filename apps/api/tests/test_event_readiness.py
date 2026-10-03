from booker_api.event_readiness import calculate_event_readiness


def test_event_readiness_counts_only_confirmed_required_positions():
    requirements = [
        {"id": "dj", "category_code": "dj", "role_label": "DJ", "qty": 2, "required": True},
        {
            "id": "photo",
            "category_code": "photo",
            "role_label": "Фотограф",
            "qty": 1,
            "required": False,
        },
    ]
    requests = [
        {
            "id": "ready",
            "requirement_id": "dj",
            "status": "Confirmed",
            "quote_id": "quote-1",
            "booking_id": "booking-1",
            "booking_status": "Confirmed",
        },
        {
            "id": "waiting",
            "requirement_id": "dj",
            "status": "AwaitingPayment",
            "quote_id": "quote-2",
            "booking_id": "booking-2",
            "booking_status": "AwaitingPayment",
        },
    ]

    readiness = calculate_event_readiness(requirements, requests)
    assert readiness["state"] == "incomplete"
    assert readiness["required_total"] == 2
    assert readiness["ready_total"] == 1
    assert readiness["missing_total"] == 1
    assert readiness["positions"] == [
        {
            "requirement_id": "dj",
            "category_code": "dj",
            "role_label": "DJ",
            "required": 2,
            "ready": 1,
            "missing": 1,
            "blocker": "not_confirmed",
        }
    ]


def test_event_readiness_reports_server_blockers_and_empty_state():
    requirements = [
        {"id": "venue", "category_code": "venue", "qty": 1, "required": True},
        {"id": "host", "category_code": "host", "qty": 1, "required": True},
    ]
    requests = [
        {
            "id": "host-request",
            "requirement_id": "host",
            "status": "RequestSent",
            "quote_id": None,
            "booking_id": None,
            "booking_status": None,
        }
    ]
    readiness = calculate_event_readiness(requirements, requests)
    blockers = {
        position["requirement_id"]: position["blocker"]
        for position in readiness["positions"]
    }
    assert blockers == {"venue": "no_request", "host": "no_offer"}
    assert calculate_event_readiness([], [])["state"] == "empty"


def test_event_readiness_keeps_completed_position_ready():
    readiness = calculate_event_readiness(
        [{"id": "venue", "category_code": "venue", "qty": 1, "required": True}],
        [
            {
                "id": "venue-request",
                "requirement_id": "venue",
                "status": "Completed",
                "quote_id": "quote",
                "booking_id": "booking",
                "booking_status": "Completed",
            }
        ],
    )
    assert readiness["state"] == "ready"
    assert readiness["ready_total"] == 1


def test_event_readiness_ignores_unlinked_cancelled_and_disputed_bookings():
    readiness = calculate_event_readiness(
        [{"id": "dj", "category_code": "dj", "qty": 1, "required": True}],
        [
            {
                "id": "unlinked",
                "requirement_id": None,
                "status": "Confirmed",
                "quote_id": "quote-unlinked",
                "booking_id": "booking-unlinked",
                "booking_status": "Confirmed",
            },
            {
                "id": "cancelled",
                "requirement_id": "dj",
                "status": "Cancelled",
                "quote_id": "quote-cancelled",
                "booking_id": "booking-cancelled",
                "booking_status": "Confirmed",
            },
            {
                "id": "disputed",
                "requirement_id": "dj",
                "status": "Confirmed",
                "quote_id": "quote-disputed",
                "booking_id": "booking-disputed",
                "booking_status": "Dispute",
            },
        ],
    )
    assert readiness["state"] == "incomplete"
    assert readiness["ready_total"] == 0
    assert readiness["missing_total"] == 1
