# MASTER_PLAN — Букер

Источник правды по продукту: [CONTRACT.md](product/CONTRACT.md). Этот файл — **журнал выполнения** плана v2.0. Не редактировать `.cursor/plans/`.

**Prod:** bukergo.ru · **master baseline:** `afcdfd5` (Event Studio Map v1)

---

## Definition of Done

- [ ] Все выполнимые P0/P1 закрыты или помечены BLOCKED с причиной
- [ ] `make lint`, `make test-api`, `make web-build`, E2E — зелёные
- [ ] Нет критических mock/stub на основном пользовательском пути (stub-платежи допустимы до гейта U5)
- [ ] Итоговый PR создан

---

## P0 — блокеры paid pilot

| ID | Задача | Статус | Доказательство |
|----|--------|--------|----------------|
| p0-contract-v2 | Product Contract v2 (ICP, state machines, monetization, «не строим») | **done** | `848c02a` — CONTRACT.md, BLUEPRINT.md |
| p0-legal-289 | Юрпакет + 289-ФЗ, OPERATOR.md, РКН, гейт U5 | **BLOCKED** | Нужны реквизиты оператора и письмо юриста; см. [OPERATOR.md](legal/OPERATOR.md) |
| p0-payment-partner | Платёжный партнёр (term sheet, 54-ФЗ, sandbox) | **BLOCKED** | Выбор партнёра — решение человека; см. [PAYMENTS_SHORTLIST.md](legal/PAYMENTS_SHORTLIST.md) |
| p0-prod-infra | Postgres, backups, restore drill, RU hosting audit | **partial** | `docs/ops/PROD_INFRA.md`, `infra/backup-booker.sh`; cron/restore/cutover pending |
| p0-security | Authz matrix, rate limits, 2FA prod, file scan | **partial** | AUTHZ_MATRIX.md, rate_limit.py; 2FA prod + AV scan pending |

---

## P1 — product + ops до PMF

| ID | Задача | Статус | Доказательство |
|----|--------|--------|----------------|
| p1-payment-adapter | Payment adapter после партнёра | **BLOCKED** | Зависит от p0-payment-partner |
| p1-analytics | Taxonomy + dashboards + client events | **pending** | частично: `/admin/metrics`, см. [ANALYTICS.md](product/ANALYTICS.md) |
| p1-supply-console | C1–C6 + iCal, completeness, templates | **partial** | C1–C6 **done** (ROADMAP); polish pending |
| p1-event-day | Critical path, replacement, offline pack | **partial** | MVP «Следующие шаги» PR #11 |
| p1-founding-supply | 80–150 профилей + 10 площадок | **BLOCKED** | Операционная задача, не код |
| p1-demand-pilots | 10→30→80 deals, case studies | **BLOCKED** | Операционная задача, не код |

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
- 2026-08-31 · **p0-prod-infra** · `4b4d554` · PROD_INFRA plan, backup-booker.sh · plan only
