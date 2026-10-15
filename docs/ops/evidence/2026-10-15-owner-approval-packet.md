# Owner approval packet — BookerGo (2026-10-15)

Один список решений. До ответов агент **не** трогает production, DNS, live payments, реальных пользователей.

## 1. Staging (блокирует T10 / T12 / P06 / O05)

**Решение владельца зафиксировано:**

- **A:** локальные тесты разрешены; **автозачёт как staging — нет**.
- **B:** remote staging DNS пуст — не найден; не используем.
- **C:** пакет предложения хоста готов — `2026-10-15-staging-host-proposal.md`. **Покупка/создание только после отдельного GO.**

Hardened local package: preflight fail-closed, standalone compose, secrets вне Git, API+web start — см. `2026-10-15-staging-hardened.md`.

## 2. SMTP / security mail (часть S06 / T07)

Нужны: тестовый SMTP host, From, mailbox для admin recovery notifications.  
Без этого delivery security notices остаётся LOCAL/disabled.

## 2b. Two-approver recovery policy (S06 / T07)

Design + fail-closed tests ready (`2026-10-15-two-approver-design.md`).  
Flag `BOOKER_TWO_APPROVER_RECOVERY_ENABLED=false` (default).  
**Нужно GO:** утвердить процедуру двух уполномоченных → затем отдельный ticket на arm execution (сейчас даже при flag=true execution `procedure_not_armed`).

## 3. Дежурный оператор (Stage E / SLA)

Павел указан как duty owner. Нужны: зарегистрированный email, канал сигнала, резервный оператор, праздничные исключения.  
До этого SLA 10:00–22:00 МСК **не** заявляется.

## 4. Design D02 / motion (Design scale)

- Figma: https://www.figma.com/design/6QGCbvU9NIW9Ba27LpDWLn  
- Motion «Рамка слота» v2: `docs/design/MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md` — статус **UNAPPROVED**  
Нужно явное: утвердить / отклонить / правки. Без GO перенос в web не делается.

## 5. Legal M06 / Payments M07–M08

Prep only. Нужны: реквизиты оператора, письмо юриста, term sheet партнёра. Live acquiring **выключен** (fail-closed).

## 6. PR merge

- PR #20 candidate `bb61e998` — draft  
- PR #22 delivery evidence — draft  
Merge только по вашему OK. Production deploy — отдельный GO.

## Уже сделано без вашего разрешения (безопасно)

- Stage A ACCEPT; local C01–C10; staging package; SQLite migrate/backup/restore rehearsal PASS  
- C04 messaging + C08 threaded exclusivity tests PASS  
- S06 dual-admin self-recovery deny VERIFIED locally  
- Scores: FULL 59 / MVP 56 / Design 15 **unchanged**
