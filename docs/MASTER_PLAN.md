# MASTER_PLAN — Букер

Источник правды по продукту: [CONTRACT.md](product/CONTRACT.md). Этот файл — **журнал выполнения** плана v2.0. Не редактировать `.cursor/plans/`.

**Prod:** bukergo.ru · **master baseline:** `afcdfd5` (Event Studio Map v1)

---

## Definition of Done

- [x] Все выполнимые P0/P1 закрыты или помечены BLOCKED с причиной (инженерия; ops/runtime p0-prod-infra — в [PROD_INFRA.md](ops/PROD_INFRA.md))
- [x] `make lint`, `make test-api`, `make web-build`, E2E — зелёные (Tick 11: 95 passed, lint ok, web-build ok, E2E 15 passed)
- [x] Нет критических mock/stub на основном пользовательском пути (stub-платежи допустимы до гейта U5)
- [x] Итоговый PR создан — [#14](https://github.com/yaacab/booker/pull/14)

---

## P0 — блокеры paid pilot

| ID | Задача | Статус | Доказательство |
|----|--------|--------|----------------|
| p0-contract-v2 | Product Contract v2 (ICP, state machines, monetization, «не строим») | **done** | `848c02a` — CONTRACT.md, BLUEPRINT.md |
| p0-legal-289 | Юрпакет + 289-ФЗ, OPERATOR.md, РКН, гейт U5 | **EXTERNAL_BLOCKED** | Нужны реквизиты оператора и письмо юриста; см. [OPERATOR.md](legal/OPERATOR.md) |
| p0-payment-partner | Платёжный партнёр (term sheet, 54-ФЗ, sandbox) | **EXTERNAL_BLOCKED** | Выбор партнёра — решение человека; см. [PAYMENTS_SHORTLIST.md](legal/PAYMENTS_SHORTLIST.md) |
| p0-prod-infra | Postgres, backups, restore drill, RU hosting audit | **done** | Alembic `a44d171`, backup/restore scripts, deploy cron; чеклисты RU audit + Postgres cutover в [PROD_INFRA.md](ops/PROD_INFRA.md). **Ops/runtime:** cron verify, prod backup, staging restore drill, cutover |
| p0-security | Authz matrix, rate limits, 2FA prod, file scan | **done** | rate limits all surfaces; ClamAV → **EXTERNAL_BLOCKED** (prod object storage) |

---

## P1 — product + ops до PMF

| ID | Задача | Статус | Доказательство |
|----|--------|--------|----------------|
| p1-payment-adapter | Payment adapter после партнёра | **EXTERNAL_BLOCKED** | Зависит от p0-payment-partner |
| p1-analytics | Taxonomy + dashboards + client events | **done** | taxonomy `53f6ddb`, funnel/liquidity/leakage dashboards |
| p1-supply-console | C1–C6 + iCal, completeness, templates | **done** | vacation mode `dffea8d`; iCal `071d5bc` |
| p1-event-day | Critical path, replacement, offline pack | **done** | check-in/out `bc72c59`; replacement `4f3a4cb`; offline-pack `88b2719` |
| p1-founding-supply | 80–150 профилей + 10 площадок | **EXTERNAL_BLOCKED** | Операционная задача, не код |
| p1-demand-pilots | 10→30→80 deals, case studies | **EXTERNAL_BLOCKED** | Операционная задача, не код |

### UI-хвосты supply console (C1–C6)

| ID | Задача | Статус | Commit |
|----|--------|--------|--------|
| C1 | Редактор состава `/events/[id]` | **done** | af2bf06 |
| C2 | UI Service | **done** | af2bf06 |
| C3 | Создание залов | **done** | af2bf06 |
| C4 | Верификация venues в админке | **done** | af2bf06 |
| C5 | confirm_another_workspace | **done** | af2bf06 |
| C6 | Analytics + e2e flow | **done** | d1bdbe3 |

### P2 polish (merged)

| PR | Фича | Статус |
|----|------|--------|
| #10 | Deal Room «Сводка» | **done** |
| #11 | Event-day ops MVP | **done** |
| #12 | Admin funnel metrics | **done** |
| #13 | Event Studio Map v1 | **done** |

---

## P2 / P3 — backlog

| ID | Задача | Статус |
|----|--------|--------|
| p2-b2b-venue-saas | B2B workspace, venue depth, supply SaaS | backlog (после 10 сделок) |
| p3-next-city | Второй город | backlog (city gate 3 мес) |

---

## Журнал выполнения

- 2026-08-31 · **p0-contract-v2** · `848c02a` · `docs/product/CONTRACT.md`, `docs/product/BLUEPRINT.md`, `docs/MASTER_PLAN.md` · journal start
- 2026-08-31 · **p0-security** · `1610998` · AUTHZ_MATRIX, rate_limit auth/webhook, tests · `make test-api` 56 passed, `make lint` ok
- 2026-08-31 · **p0-prod-infra** · `85cc979` · PROD_INFRA plan, backup-booker.sh · plan only
- 2026-08-31 · **p1-analytics** · `8bdf1b3` · client events API + trackClientEvent · `make test-api` 59 passed, `make web-build` ok
<!-- commits below added by execution loop -->
- 2026-08-31 · **p0-security** · `4cdf7d8` · 2FA enforce, file_scan, attachments API · `make test-api` 66 passed, lint ok
- 2026-08-31 · **p0-prod-infra** · `03ac1b1` · restore-drill.sh, cron example · script smoke via pytest suite
- 2026-08-31 · **p1-analytics** · `f89ccf3` · client.event metrics + search/deal tracking · E2E 13 passed, web-build ok
- 2026-08-31 · **p1-supply-console** · `eb96f43` · supply-completeness API + cabinet · `make test-api` 69 passed
- 2026-08-31 · **p1-event-day** · `88b2719` · offline-pack export · test_offline_pack
- 2026-09-01 · **p0-prod-infra** · `dab06a9` · backup cron on deploy
- 2026-09-01 · **p1-analytics** · `f23f349` · by_event metrics + analytics rate limit · 70 tests
- 2026-09-01 · **p1-event-day** · `6a39426` · replacement CTA in Control Room
- 2026-09-01 · **p1-supply-console** · `881626d` · service templates API + cabinet
- 2026-09-01 · **p0-prod-infra** · `3a1e60f` · restore-drill smoke test
- 2026-09-01 · **p0-security** · `4c07316` · admin TOTP enable + page.view · 73 tests
- 2026-09-01 · **p1-supply-console** · `071d5bc` · iCal busy import API + cabinet · `make test-api` 77 passed, lint ok
- 2026-09-01 · **p1-event-day** · `4f3a4cb` · replacement plan API, booking cancel, catalog exclude, Control Room panel · `make test-api` 80 passed, lint ok
- 2026-09-01 · **p1-supply-console** · `dffea8d` · vacation mode API + cabinet · `make test-api` 85 passed, lint ok
- 2026-09-01 · **p1-event-day** · `bc72c59` · check-in/out API + Control Room day panel · `make test-api` 90 passed, lint ok
- 2026-09-01 · **p0-prod-infra** · `a8b8a5b` · journal Alembic baseline · `make test-api` 92 passed, lint ok
- 2026-09-01 · **p1-analytics** · `53f6ddb` · cabinet/studio taxonomy + funnel/liquidity/leakage dashboards · `make test-api` 94 passed, lint ok
- 2026-09-01 · **p0-security** · `a7ba5dc` · upload/admin/messaging rate limits; ClamAV EXTERNAL_BLOCKED · `make test-api` 95 passed, lint ok
- 2026-09-01 · **p0-prod-infra** · `ed0be4f` · PROD_INFRA RU hosting audit + Postgres cutover checklists · test-api 95, lint ok, web-build ok, E2E 15 · ops/runtime only remains
- 2026-09-01 · **web-build** · `d895b80` · admin funnel metric row type fix · web-build green
- 2026-09-01 · **tick-12** · engineering complete · branch `feat/master-plan-execution` PR-ready (+28 commits); DoD закрыт — PR [#14](https://github.com/yaacab/booker/pull/14) · pre-PR checks: test-api 95 passed (1 skipped), lint ok, web-lint ok, web-build ok, E2E 15 passed
