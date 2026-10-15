# C04 / C08 deepened (LOCAL)

Date: 2026-10-15  
SHA: (commit)  
Log: `c04-c08-s06.log`

| ID | Test | Result |
|---|---|---|
| C04 | `test_c04_deal_message_create_peer_sees_reload_stranger_denied` | PASS |
| C08 | `test_c08_threaded_hold_exclusivity_same_slot` | PASS |

Limitations: SQLite TestClient threads ≠ Postgres staging race. Staging scores unchanged.
