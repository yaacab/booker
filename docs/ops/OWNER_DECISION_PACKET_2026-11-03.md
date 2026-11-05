# OWNER DECISION PACKET — 2026-11-03

Короткий список **реально нужных** решений. Без ложных зависимостей на production.

## Разделить три GO

| ID | Решение | Не путать с |
|---|---|---|
| `OWN-STAGING-GO` | ✅ GO записан 05.11.2026; **хост/DNS ещё нужны** → `REL-STAGING-HOST` | production |
| `OWN-GIT-INTEGRATION-GO` | ✅ DONE — PR #28 merged → `master` `3f52b58` | production deploy |
| `OWN-PROD-GO` | Только production release — **ещё TODO** | staging и git-canonical |

`OWN1` уже DONE = packet A/B/C записан, **не** Infra C GO.

## Секреты и доступ

| ID | Нужно |
|---|---|
| `OWN-SMTP` | ⏳ GO есть; нужны значения → `SECRETS_INTAKE_OAUTH_SMTP_2026-11-05.md` |
| `OWN-TWO-APPROVER` | Два утверждающих staff recovery |
| `OWN-OAUTH-YANDEX-VK` | ⏳ GO есть; нужны значения → тот же intake |

## Дизайн / motion

| ID | Нужно |
|---|---|
| `OWN-DESIGN-ACK` | ✅ DONE 05.11.2026 (DRAFT pack); V04 pixel Figma ещё открыт |
| `OWN-MOTION-ACK` | Утвердить конкретный motion «Рамка слота» — ещё TODO |

## Право / деньги / пилот (не трогаем кодом)

| ID | Нужно |
|---|---|
| `OWN-LEGAL-GO` | Юрист/бухгалтер/реквизиты → legal publish |
| `OWN-PAY-PARTNER` | Письменная схема платежей/чеков |
| `OWN-PILOT` | Founding supply/demand pilot |

## Что уже не требует этих GO

- Локальные V0/V3/hold/calendar тесты в feature-ветке.  
- Локальный V07 viewport/keyboard/Lighthouse (формальный design DONE всё ещё ждёт motion ack).  
- DRAFT матрица V04 (Home/Deal + Event Studio 2–5 + Control Room card states) и Artist vNext storyboards 1–10 в `docs/design/` без переноса в web.  
- AUTH stubs/Telegram/sessions локально (live Yandex/VK — только после OAuth secrets + staging).  
- Локальные public shells V07: artist/compare/legal/faq/for-artists/support/privacy @390.

## Не включать в этот packet

Повторные «нужен production», live payments, опасные prod-миграции, РКН/хостинг 152-ФЗ (`LEG-03`) — отдельные треки.
