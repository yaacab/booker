# Stage C — Acceptance scenarios (candidate `bb61e998`)

Level: **локально** (isolated SQLite + Playwright production web).  
Staging: **BLOCKED** — see `../2026-10-15-staging-discovery.md`.  
Logs: `api-critical.log`, `api-acceptance-suite.log` (72 PASS), `browser-acceptance.log` (18 PASS).

Status legend: PASS / FAIL / BLOCKED (staging-only aspects marked BLOCKED with local PASS note).

---

## C01 — Создание события

| Field | Value |
|---|---|
| Preconditions | Isolated API/web; demo seed / fixture registration |
| Actions | Create event via API/UI in deal-path / flow / cabinets-cross-role |
| Expected | Event created, owned by customer org |
| Actual | Events created in browser suite + API offer setup |
| Evidence | `browser-acceptance.log` (deal-path, flow, cabinets-cross-role); API suite |
| Result | **PASS** (локально) |

## C02 — Выбор артиста или площадки

| Field | Value |
|---|---|
| Preconditions | Catalog seed / published artist in fixtures |
| Actions | Search filters + attach resource on request |
| Expected | Artist/venue selectable; request binds resource_id |
| Actual | `search-filters.spec.ts` + deal-path request create PASS |
| Evidence | browser log; API catalog covered historically / request posts in deal-path |
| Result | **PASS** (локально) |

## C03 — Отправка заявки

| Field | Value |
|---|---|
| Preconditions | Event + resource |
| Actions | POST `/events/{id}/requests` (E07) |
| Expected | Single request entity visible to both sides |
| Actual | E07 PASS |
| Evidence | `e2e/deal-path.spec.ts` in browser log |
| Result | **PASS** (локально) |

## C04 — Deal Room и переписка

| Field | Value |
|---|---|
| Preconditions | Booking/deal after offer |
| Actions | Open deal room; messaging / support assistant navigation |
| Expected | Deal room loads; messages/support sessions work |
| Actual | deal-room GETs + support assistant sessions in browser log; cabinets-cross-role PASS |
| Evidence | browser-acceptance.log |
| Result | **PASS** (локально) |

## C05 — Предложение и серверная цена по `quote_id`

| Field | Value |
|---|---|
| Preconditions | Offer created |
| Actions | Ack with `quote_id`; quote versioning tests |
| Expected | Server binds price to quote_id; stale quote rejected |
| Actual | `test_quote_versioning.py` PASS; E07/E08 use quote_id |
| Evidence | api-acceptance-suite.log; deal-path E08 |
| Result | **PASS** (локально) |

## C06 — Подтверждение необходимых сторон

| Field | Value |
|---|---|
| Preconditions | Offer version |
| Actions | Supplier + customer ack; re-ack after new version (E08) |
| Expected | Hold blocked until both ack current quote; after re-ack hold allowed |
| Actual | E08 PASS |
| Evidence | browser-acceptance.log deal-path E08 |
| Result | **PASS** (локально) |

## C07 — Создание бронирования (hold)

| Field | Value |
|---|---|
| Preconditions | Mutual ack |
| Actions | POST hold on booking |
| Expected | Active hold created |
| Actual | Holds tests + E09 first winner 200 |
| Evidence | `test_holds.py`, deal-path E09, test_hold_race |
| Result | **PASS** (локально) |

## C08 — Запрет второй конфликтующей брони (+ конкурентность)

| Field | Value |
|---|---|
| Preconditions | Two negotiated bookings same slot |
| Actions | Two hold attempts (API exclusivity + E09) |
| Expected | Exactly one 200 and one 409; one active hold |
| Actual | `test_concurrent_hold_same_slot_only_one_succeeds` PASS; E09 PASS |
| Evidence | api-critical.log; browser deal-path E09 |
| Result | **PASS** (локально) |

Note: SQLite TestClient path verifies exclusivity; true OS-thread race noted in test docstring — acceptable for local gate; staging concurrency remains open.

## C09 — Поддержка и оператор

| Field | Value |
|---|---|
| Preconditions | Customer + staff fixtures |
| Actions | Support assistant; admin support queue; operator role API |
| Expected | Ticket/assistant path works; operator role enforced |
| Actual | `admin-support-queue.spec.ts`, `support-assistant.spec.ts` PASS; operator/security API PASS |
| Evidence | browser-acceptance.log; api-acceptance-suite.log |
| Result | **PASS** (локально). Real SMTP/Telegram delivery **not** claimed. |

## C10 — Роли, права, изоляция

| Field | Value |
|---|---|
| Preconditions | Multi-org fixtures |
| Actions | Authz regressions; org-switch; cross-role cabinets |
| Expected | Cross-tenant denial; session pin on org switch |
| Actual | authz suites PASS; org-switch + cabinets-cross-role PASS |
| Evidence | api-acceptance-suite.log; browser-acceptance.log |
| Result | **PASS** (локально) |

---

## Summary

| ID | Result |
|---|---|
| C01–C10 | PASS локально |
| Staging mobile full path (T12/P06) | BLOCKED (no staging host) |

No FAIL requiring Stage D code fix from this run.
