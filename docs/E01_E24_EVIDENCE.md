# E01–E24 Evidence — Spec v3 G2 candidate

**Candidate SHA:** `ef1f83b7e6d4dbba12e372b9f68b38b09e4f78d2` (`ef1f83b`)  
**Branch (evidence worktree):** `agent/w5-evidence` (base integration `feat/master-plan-execution`)  
**Date:** 2026-09-06  
**G2 status:** **не закрыт** — таблица evidence заполнена; манифест/скриншоты 3 ролей/полный CI e2e deal-path ещё открыты.  
**E25:** **ожидает G3** (prod smoke только с OK владельца).  
**Explicit non-claims:** live PSP / map provider / SMS-push **не** заявляются; stub ≠ real PSP.

Результаты: `PASS` | `PARTIAL` | `FAIL` | `OWNER_BLOCKED` | `ожидает G3`.

Команды (локально / CI):

```bash
# API
cd apps/api && pytest -q tests/test_<name>.py

# Critical e2e (как в .github/workflows/ci.yml e2e-critical)
cd apps/web && npx playwright test \
  e2e/event-studio-map.spec.ts \
  e2e/supply-nav.spec.ts \
  e2e/search-filters.spec.ts

# Deal-path / cabinets / a11y (есть в repo, не все в CI critical list)
npx playwright test e2e/flow.spec.ts e2e/cabinets-cross-role.spec.ts e2e/cabinet-a11y.spec.ts
```

---

## Evidence table

| ID | Scenario (spec §27.1) | Command / test path | Result | SHA / commit evidence | Notes |
| ---- | ---- | ---- | ---- | ---- | ---- |
| E01 | Гость ищет артиста на дату, затем входит — фильтры и кандидат сохраняются | `pytest apps/api/tests/test_catalog_search_filters.py::test_search_artist_format_travel_budget`; `apps/web/e2e/search-filters.spec.ts` (filters + home dual search); filters live in URL (`CatalogFilters` → `/search?...`) | **PARTIAL** | `6adf8c7` Wave 1; base `ef1f83b` | Фильтры/поиск покрыты API+e2e. Нет dedicated e2e «гость → login → тот же кандидат»; persistence через query URL, не отдельный post-login restore тест. |
| E02 | Поиск зала на 80 гостей с рассадкой | `test_catalog_search_filters.py::test_search_venue_guests_matching_halls`; e2e `search-filters` home → `guests=80` | **PASS** | `6adf8c7` | Map provider list-only без ключа — Contour C, не блокирует E02 list search. |
| E03 | Неизвестный/синтетический календарь — нет «подтверждённо свободно» | `test_catalog_search_filters.py::test_search_synthetic_venue_flag_present`; e2e `search-filters` «календарь ориентировочный» | **PASS** | `6adf8c7` | |
| E04 | Избранное/состав — нет брони/hold/рассылки | `pytest apps/api/tests/test_favorites.py` (`test_favorites_e04_no_booking_hold_request`) | **PASS** | `8715009` / `71cbb23` | |
| E05 | Event Studio flag on/off + rollback | `apps/web/e2e/event-studio-map.spec.ts` (default OFF classic; `?event_studio_map_v1=1` map); CI critical | **PASS** | `fb24377` | Flag default OFF; URL override / env rebuild per RELEASE_MANIFEST rollback. |
| E06 | Autosave, reload, login, offline/retry | e2e `event-studio-map` «E06: autosave переживает reload»; draft in `localStorage` | **PARTIAL** | `e578301` / `fb24377` | Reload autosave PASS. Offline/retry и login-without-duplicate event — без dedicated e2e на этом SHA. |
| E07 | Заказчик → запрос → поставщик → оффер (одна сущность) | API offer path via `test_offers` / negotiation helpers; e2e `flow.spec.ts` «заявка → оффер»; `cabinets-cross-role.spec.ts` full cycle | **PARTIAL** | deal path exists; polish open (`W2-DEAL-PATH`) | Happy path UI+API есть. `cabinets-cross-role` **не** в CI `e2e-critical` list (только map/supply/search). |
| E08 | Новая версия оффера — старые ack невалидны | `pytest apps/api/tests/test_quote_versioning.py`; e2e cross-role step «E08: новая версия…» | **PARTIAL** | quote tests on base; e2e polish | API PASS. E2E покрывает bump+re-ack в cross-role, но не в critical CI. |
| E09 | Две параллельные попытки hold | `pytest apps/api/tests/test_hold_race.py::test_concurrent_hold_same_slot_only_one_succeeds`; `test_holds.py::test_parallel_hold_conflict` | **PARTIAL** | hold race on base | API exclusivity PASS (sequential client; true thread-race limited on SQLite). Нет dedicated concurrent e2e. |
| E10 | Multi-hall atomic — нет частичного захвата | `pytest apps/api/tests/test_multi_hall_atomic.py` | **PASS** | `449e7e8` | |
| E11 | Истечение hold / перенос / отмена | `test_holds.py::test_expired_hold_frees_slot`; `test_replacement.py`; e2e cross-role cancel artist ≠ venue hold | **PASS** | hold/replacement tests; cross-role cancel | |
| E12 | Фальшивый redirect оплаты + duplicate webhook | `pytest apps/api/tests/test_payments.py` (`test_failed_webhook_does_not_confirm`, `test_webhook_idempotent_and_confirms_once`); `test_payment_adapter.py` stub default | **PARTIAL** | payments stub on base | Duplicate/failed webhook на **stub** PASS. Live redirect / real PSP = Contour **C-LIVE** → не claimed. stub ≠ PSP. |
| E13 | External-paid + audit | `pytest apps/api/tests/test_external_payment_confirm.py` | **PASS** | `e578301` | Operator confirm + audit; stub≠PSP explicit in test docstring. |
| E14 | Частичный/повторный возврат | `test_authz_regressions.py::test_refund_guards_status_and_idempotency`; admin `/admin/refunds` | **PARTIAL** | authz refunds on base | Идемпотентный full refund PASS. Admin path всегда `amount_rub=payment.amount_rub` (partial amount не exercised). Live refund adapter = **C-PAY-WH** OWNER_BLOCKED. |
| E15 | Три роли + переключение организаций | e2e `cabinets-cross-role` (customer/performer/venue shells); `test_workspace.py::test_active_org_and_performer_alias` | **PARTIAL** | `1d01330` cabinets; workspace API | Разные кабинеты/навигация PASS в e2e. Org switch API+audit PASS; dedicated UI org-switch e2e thin. |
| E16 | «Календарь» ≠ «Заявки» на мобильном | `apps/web/e2e/supply-nav.spec.ts` (390 px performer; venue sections); CI critical | **PASS** | `fb24377` | |
| E17 | Чужой ID сделки/файла/зала | `test_authz_regressions.py`; `test_idor_events.py`; `test_halls.py::test_public_halls_require_catalog_or_member`; attachments auth in `test_attachments.py` | **PASS** | authz suite on base | Expand backlog (`W5-AUTHZ` IN_PROGRESS) — core IDOR/forbid covered. |
| E18 | Публичный бриф ≠ приватное событие | `pytest apps/api/tests/test_briefs.py::test_brief_linked_event_does_not_leak_private_fields` (+ publish/list) | **PASS** | `4bf519a` / `a16a418` | |
| E19 | Отклик на бриф → контрактная модель | `test_briefs.py::test_publish_list_respond_close` (antispam/close 409); OfferVersion via existing deal path | **PASS** | `4bf519a` | |
| E20 | Отзыв / claim / модерация | `pytest apps/api/tests/test_reviews.py`; `test_trust_outbox.py` claim/support | **PASS** | `51214da` reviews; `700f2c1` claim/support | Reviews only after Completed. |
| E21 | Ошибка email / retry без дублей | `test_trust_outbox.py::test_email_outbox_retry_idempotent` | **PASS** | `700f2c1` | SMTP optional; unit/idempotent outbox. |
| E22 | Revoke shared link | `pytest apps/api/tests/test_shortlists.py` (`test_create_public_share_and_revoke`) | **PASS** | `700f2c1` | |
| E23 | Restore from backup | `pytest apps/api/tests/test_backup_restore.py`; `docs/ops/RESTORE_DRILL_LOG.md` row 2026-09-06 PASS; `infra/restore-drill.sh` | **PASS** | `ea46dca` drill log; backup tests on base | Prod VPS isolated `/tmp` drill PASS; uploads included in smoke. |
| E24 | 390 px + keyboard + screen reader | `apps/web/e2e/cabinet-a11y.spec.ts`; supply-nav 390; event-studio mobile 390; screenshots `docs/screenshots/event-studio-map-v1/{desktop-1440,mobile-390}.png` | **PARTIAL** | `3c7c3fc` a11y; map screenshots | Keyboard/landmarks/skip links PASS for cabinets. Нет полного SR audit + screenshots **1440/390 × 3 roles** (manifest checkbox open). |
| E25 | Production release smoke | — | **ожидает G3** | — | Owner OK + prod; не часть G2 close. |

---

## Manifest checkbox sources

Pointers for coordinator (`docs/RELEASE_MANIFEST.md` — **do not edit here**):

| Manifest checklist item | Supporting evidence |
| ---- | ---- |
| CI green on candidate SHA (unit + critical e2e) | `.github/workflows/ci.yml` → `pytest` + `e2e-critical` (map/supply/search). Deal-path/cross-role **not** in critical list → do not tick until expanded or separately green. |
| Screenshots 1440/390 × 3 roles | Only Event Studio map: `docs/screenshots/event-studio-map-v1/`. **Incomplete** for 3 cabinets. |
| Сквозной сценарий заявка→оффер на SHA | `apps/web/e2e/flow.spec.ts` + `cabinets-cross-role.spec.ts`; API quote/hold. Mark when run on **this** SHA / CI includes them. |
| E01–E24 table filled; E25 = ожидает G3 | **This file** (`docs/E01_E24_EVIDENCE.md`). |
| No open mandatory A/B | Contour C (`C-LIVE`/`C-MAP`/`C-SMS`) OWNER_BLOCKED ≠ done; Wave 2 deal-path e2e polish + Wave 5 screenshots/manifest still open → **G2 not closed**. |
| a11y proof | E24 row + `cabinet-a11y.spec.ts` (PARTIAL). |
| backup proof | E23 row + `RESTORE_DRILL_LOG.md` PASS 2026-09-06 + `test_backup_restore.py`. |

---

## Counts (honest)

| Result | IDs |
| ---- | ---- |
| PASS | E02, E03, E04, E05, E10, E11, E13, E16, E17, E18, E19, E20, E21, E22, E23 (**15**) |
| PARTIAL | E01, E06, E07, E08, E09, E12, E14, E15, E24 (**9**) |
| OWNER_BLOCKED (contour aspects noted in PARTIAL rows) | live PSP/map/SMS — not separate E-rows; see C-* backlog |
| ожидает G3 | E25 (**1**) |
| FAIL | none recorded on this pass |

**Blockers to G2 close (evidence lens):** deal-path e2e not in CI critical; screenshots ×3 roles missing; RELEASE_MANIFEST checkboxes coordinator-owned; Contour C must stay disabled/non-claimed.
