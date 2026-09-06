# Spec v3 — Delivery Backlog

Статусы: `TODO` | `IN_PROGRESS` | `IN_REVIEW` | `VERIFIED` | `OWNER_BLOCKED` | `ENV_BLOCKED` | `READY_FOR_RELEASE`

Цель: **G2** только если **все A+B** закрыты. `OWNER_BLOCKED` не заменяет критерий. E25 = ожидает G3. Merge/prod — OK владельца.

Evidence при закрытии: реализация → тест → результат → SHA → ограничения.

| ID | Требование | Pri | Deps | Owner | Status | Acceptance | Test | Commit/PR | Blocker |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| DOC-GAP | Gap + spec в repo | P0 | — | coord | VERIFIED | docs | review | f1a3298 | — |
| DOC-CONTRACT | CONTRACT discovery + reviews/claims | P0 | DOC-GAP | coord | VERIFIED | CONTRACT | review | f1a3298 | — |
| W0-FLAG | Flag query→env→default OFF | P0 | — | web | VERIFIED | E05 | unit+e2e | fb24377 | — |
| W0-CI | CI master; e2e на SHA PR | P0 | — | ops | VERIFIED | CI on branch SHA | CI | fb24377 | — |
| W0-NAV | Calendar ≠ Requests URLs | P0 | — | web | VERIFIED | E15 E16 | e2e | fb24377 | — |
| W0-CAB-ROUTES | cabinet section routes | P0 | W0-NAV | web | VERIFIED | sections | e2e | fb24377 | — |
| W1-SEARCH-ART | Filters format/travel/budget | P0 | — | api+web | VERIFIED | E01 | api+e2e | pending | — |
| W1-SEARCH-VEN | Hall capacity/equipment | P0 | — | api+web | VERIFIED | E02 E03 | api+e2e | pending | map OWNER |
| W1-SEO | metadata + sitemap | P0 | — | web | VERIFIED | SEO | unit | pending | — |
| W1-HOME | Home dual search | P0 | W1-SEARCH | web | VERIFIED | §4.1 | e2e | pending | — |
| W2-ONBOARD | Role onboarding | P0 | — | web+api | TODO | §5 | e2e | — | — |
| W2-CAB-CUST | Customer scenarios | P0 | W0-CAB | web | TODO | §11.2 | e2e 3 roles | — | — |
| W2-CAB-PERF | Performer scenarios | P0 | W0-CAB | web | TODO | §12 | e2e | — | — |
| W2-CAB-VEN | Venue scenarios | P0 | W0-CAB | web | TODO | §13 | e2e | — | — |
| W2-AUTOSAVE | Studio autosave | P0 | W0-FLAG | web | TODO | E06 | e2e | — | — |
| W2-DEAL-PATH | Request→offer→hold | P0 | — | api+web | TODO | E07–E09 | e2e | — | — |
| W2-MULTI-HALL | Atomic multi-hall | P1 | W2-DEAL | api | TODO | E10 | race | — | — |
| W2-CANCEL | Transfer/cancel | P1 | W2-DEAL | api | TODO | E11 | api | — | — |
| W2-EXT-PAY | External confirm UX/audit | P0 | — | api+web | TODO | E13 no fake online | e2e | — | — |
| W3-FAV | Favorites | P1 | — | api+web | TODO | E04 | api+e2e | — | — |
| W3-COMPARE | Compare | P1 | W3-FAV | web | TODO | §10 | e2e | — | — |
| W3-SHARE | Shared + revoke | P1 | W3-FAV | api+web | TODO | E22 | api+e2e | — | — |
| W3-SAVED | Saved search + consent | P1 | notif | api+web | TODO | §10 | api | — | — |
| W3-BRIEF | Public briefs | P1 | — | api+web | TODO | E18 E19 | e2e | — | — |
| W3-PROMO | Share/QR/funnel | P1 | — | web+api | TODO | §15.1 | e2e | — | — |
| W4-MSG-HUB | Message center | P1 | — | web+api | TODO | §19 | e2e | — | — |
| W4-NOTIF | Email outbox retry | P1 | EMAIL | api | TODO | E21 | unit | — | EMAIL_* |
| W4-REVIEW | Reviews after Completed | P1 | — | api+web | TODO | E20 | api | — | — |
| W4-CLAIM | Venue ownership claim | P1 | — | api+web | TODO | §20 | api | — | — |
| W4-SUPPORT | Support/complaints | P1 | — | api+web | TODO | §20–21 | api | — | — |
| W5-AUTHZ | Authz regression | P0 | — | qa | TODO | E17 | api | — | — |
| W5-E2E-PR | Critical e2e in PR | P0 | W0-CI | qa | TODO | entry+cabinets+deal+flag | CI on SHA | — | — |
| W5-A11Y | Mobile 390 a11y | P1 | — | qa | TODO | E24 | e2e | — | — |
| W5-BACKUP | DB+files restore | P1 | — | ops | TODO | E23 | drill | — | — |
| W5-MANIFEST | RELEASE_MANIFEST | P0 | waves | coord | TODO | G2 pack | review | — | — |
| W5-E25 | Prod smoke | G3 | owner | ops | TODO | E25 | prod | — | ожидает G3 |
| C-LIVE | Live provider | C | OWNER | api | OWNER_BLOCKED | sandbox | — | — | PAYMENT_PARTNER |
| C-MAP | Map provider | C | OWNER | web | OWNER_BLOCKED | §7 | — | — | MAP_PROVIDER |
| C-SMS | SMS/push | C | OWNER | api | OWNER_BLOCKED | — | — | — | SMS_* |
| C-PAY-WH | Provider webhook/refund tests | C | C-LIVE | qa | OWNER_BLOCKED | sandbox | — | — | live adapter |

## Параллельный реестр (заполняет координатор)

| Задача | Агент | Worktree/ветка | Base SHA | Ownership | Deps | Статус | Тесты | Интеграция |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| — | — | — | — | — | — | ожидает Agent | — | — |

## Порядок волн

0 baseline → 1 search/vitrines → 2 cabinets/deals → 3 discovery B → 4 trust → 5 harden/G2.
