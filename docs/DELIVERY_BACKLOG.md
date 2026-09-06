# Spec v3 — Delivery Backlog

Статусы: `TODO` | `IN_PROGRESS` | `IN_REVIEW` | `VERIFIED` | `OWNER_BLOCKED` | `ENV_BLOCKED` | `READY_FOR_RELEASE`

Цель: **G2** только если **все A+B** закрыты. `OWNER_BLOCKED` / `ENV_BLOCKED` **не** заменяют критерий. E25 = ожидает G3. Merge/prod — OK владельца.

Evidence при закрытии: реализация → тест → результат → SHA → ограничения.

Параллель: max полезных агентов; worktree+ветка от fixed SHA; non-overlapping ownership; shared files → coordinator; отдельные test DB/ports/uploads; sequential integrate; примеры направлений ≠ потолок числа агентов; при нехватке слотов — та же очередь доступными средствами.

| ID | Требование | Pri | Deps | Owner | Status | Acceptance | Test | Commit/PR | Blocker |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| DOC-GAP | Gap + spec в repo | P0 | — | coord | VERIFIED | docs | review | f1a3298 | — |
| DOC-CONTRACT | CONTRACT discovery + reviews/claims | P0 | DOC-GAP | coord | VERIFIED | CONTRACT | review | f1a3298 | — |
| W0-FLAG | Flag query→env→default OFF | P0 | — | web | VERIFIED | E05 | unit+e2e | fb24377 | — |
| W0-CI | CI master; e2e на SHA PR | P0 | — | ops | VERIFIED | CI on branch SHA | CI | fb24377 | — |
| W0-NAV | Calendar ≠ Requests URLs | P0 | — | web | VERIFIED | E15 E16 | e2e | fb24377 | — |
| W0-CAB-ROUTES | cabinet section routes | P0 | W0-NAV | web | VERIFIED | sections | e2e | fb24377 | — |
| W1-SEARCH-ART | Filters format/travel/budget | P0 | — | api+web | VERIFIED | E01 | api+e2e | 6adf8c7 | — |
| W1-SEARCH-VEN | Hall capacity/equipment | P0 | — | api+web | VERIFIED | E02 E03 | api+e2e | 6adf8c7 | map OWNER |
| W1-SEO | metadata + sitemap | P0 | — | web | VERIFIED | SEO | unit | 6adf8c7 | — |
| W1-HOME | Home dual search | P0 | W1-SEARCH | web | VERIFIED | §4.1 | e2e | 6adf8c7 | — |
| W2-ONBOARD | Role onboarding | P0 | — | web+api | VERIFIED | §5 | e2e | onboarding.spec | — |
| W2-CAB-CUST | Customer scenarios | P0 | W0-CAB | web | IN_PROGRESS | §11.2 | e2e | e578301 | depth |
| W2-CAB-PERF | Performer scenarios | P0 | W0-CAB | web | IN_PROGRESS | §12 | e2e | shells | depth |
| W2-CAB-VEN | Venue scenarios | P0 | W0-CAB | web | IN_PROGRESS | §13 | e2e | shells | depth |
| W2-AUTOSAVE | Studio autosave | P0 | W0-FLAG | web | VERIFIED | E06 reload | e2e | studio-autosave | offline thin |
| W2-DEAL-PATH | Request→offer→hold | P0 | — | api+web | VERIFIED | E07–E09 | api+e2e | deal-path in CI | — |
| W2-MULTI-HALL | Atomic multi-hall | P1 | W2-DEAL | api | VERIFIED | E10 | race | 449e7e8 | — |
| W2-CANCEL | Transfer/cancel | P1 | W2-DEAL | api | VERIFIED | E11 | api | test_replacement | — |
| W2-EXT-PAY | External confirm UX/audit | P0 | — | api+web | VERIFIED | E13 no fake online | api | e578301 | stub≠PSP |
| W3-FAV | Favorites | P1 | — | api+web | VERIFIED | E04 | api | 8715009 | — |
| W3-COMPARE | Compare | P1 | W3-FAV | web+api | VERIFIED | §10 | api | pending | — |
| W3-SHARE | Shared + revoke | P1 | W3-FAV | api+web | VERIFIED | E22 | api | pending | — |
| W3-SAVED | Saved search + consent | P1 | notif | api+web | VERIFIED | §10 | api | 4e262ab / 1f6d5cc | — |
| W3-BRIEF | Public briefs | P1 | — | api+web | VERIFIED | E18 E19 | api | 4bf519a | — |
| W3-PROMO | Share/QR/funnel | P1 | — | web+api | VERIFIED | §15.1 | api | c052b61 / 60cf8ee | — |
| W4-MSG-HUB | Message center | P1 | — | web+api | VERIFIED | §19 | api | 15d5880 | e2e optional expand |
| W4-NOTIF | Email outbox retry | P1 | EMAIL | api | VERIFIED | E21 | unit | pending | SMTP optional |
| W4-REVIEW | Reviews after Completed | P1 | — | api+web | VERIFIED | E20 | api | 51214da | — |
| W4-CLAIM | Venue ownership claim | P1 | — | api+web | VERIFIED | §20 | api | pending | — |
| W4-SUPPORT | Support/complaints | P1 | — | api+web | VERIFIED | §20–21 | api | pending | — |
| W5-AUTHZ | Authz regression | P0 | — | qa | IN_PROGRESS | E17 | api | test_authz_* | expand |
| W5-E2E-PR | Critical e2e in PR | P0 | W0-CI | qa | IN_PROGRESS | entry+cabinets+deal+flag+a11y | CI | expanded list | await PR green |
| W5-A11Y | Mobile 390 a11y | P1 | — | qa | VERIFIED | E24 | e2e | cabinet-a11y 390×3 + g2-roles shots | SR manual residual |
| W5-BACKUP | DB+files restore | P1 | — | ops | VERIFIED | E23 | drill+pytest | ea46dca + test_backup_restore | RESTORE_DRILL_LOG PASS 2026-09-06 |
| W5-MANIFEST | RELEASE_MANIFEST | P0 | waves | coord | IN_PROGRESS | G2 pack | review | draft | CI green + residual A/B PARTIAL open |
| W5-E25 | Prod smoke | G3 | owner | ops | TODO | E25 | prod | — | ожидает G3 |
| C-LIVE | Live provider | C | OWNER | api | OWNER_BLOCKED | sandbox | — | — | PAYMENT_PARTNER |
| C-MAP | Map provider | C | OWNER | web | OWNER_BLOCKED | §7 | — | — | MAP_PROVIDER |
| C-SMS | SMS/push | C | OWNER | api | OWNER_BLOCKED | — | — | — | SMS_* |
| C-PAY-WH | Provider webhook/refund tests | C | C-LIVE | qa | OWNER_BLOCKED | sandbox | — | — | live adapter |

## Параллельный реестр

Base SHA для новых worktree: текущий integration HEAD после commit. Integration: `feat/master-plan-execution`.

| Задача | Агент | Worktree/ветка | Base SHA | Ownership | Deps | Статус | Тесты | Интеграция |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| W0-* | coord | main wt | fb24377 | features.ts, ci.yml, SiteChrome, cabinetRoutes | — | VERIFIED | unit+e2e | merged |
| W1-* | coord | main wt | 6adf8c7 | catalog search, home, SEO | W0 | VERIFIED | api+e2e | merged |
| W3-FAV | agent-fav | w3-fav | b2f6dc8 | favorites | — | VERIFIED | api | 8715009 |
| W3-BRIEF | agent-brief | w3-brief | 12e4192 | briefs | — | VERIFIED | api | 4bf519a |
| W4-REVIEW | agent-rev | w4-review | ef27bdd | reviews | — | VERIFIED | api | 51214da |
| W3-SHARE+COMPARE+W4-CLAIM/SUPPORT/NOTIF | coord | main wt | 4bf519a | shortlists, trust, outbox, compare/support UI | fav | VERIFIED | api 14 | this commit |
| W2-CAB-PERF | — | — | HEAD | cabinet/performer/** | W0 | QUEUED | e2e | — |
| W2-CAB-VEN | — | — | HEAD | cabinet/venue/** | W0 | QUEUED | e2e | — |
| W4-MSG-HUB | coord | main wt | 15d5880 | messages hub | deals | VERIFIED | api | integrated |
| W3-SAVED+PROMO | agents | main wt | 4e262ab/c052b61 | saved search, QR | — | VERIFIED | api | integrated |
| W5-EVIDENCE | agent/w5-evidence | w5-evidence | ef1f83b | E01_E24_EVIDENCE, DELIVERY_* | — | IN_PROGRESS | docs | this branch |
| W5-MANIFEST | coord | main wt | after A+B | RELEASE_MANIFEST | waves | IN_PROGRESS | review | draft checkboxes open |

Shared (только coord): migrations, auth, OpenAPI/types, SiteChrome, lockfile, CI, globals.css, features.ts.

## Порядок волн

0 baseline → 1 search/vitrines → 2 cabinets/deals → 3 discovery B → 4 trust → 5 harden/G2.
