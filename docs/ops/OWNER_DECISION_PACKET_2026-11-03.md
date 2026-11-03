# OWNER DECISION PACKET — 2026-11-03

Короткий список **реально нужных** решений. Без ложных зависимостей на production.

## Разделить три GO

| ID | Решение | Не путать с |
|---|---|---|
| `OWN-STAGING-GO` | Хост + DNS + доступ к staging для измерений/E2E/миграций | production |
| `OWN-GIT-INTEGRATION-GO` | Merge принятых фич (PR #28 / V0+V3) в delivery/live canonical | production deploy |
| `OWN-PROD-GO` | Только production release | staging и git-canonical |

`OWN1` уже DONE = packet A/B/C записан, **не** Infra C GO.

## Секреты и доступ

| ID | Нужно |
|---|---|
| `OWN-SMTP` | Рабочий SMTP для recovery/security notifications |
| `OWN-TWO-APPROVER` | Два утверждающих staff recovery |
| `OWN-OAUTH-YANDEX-VK` | `client_id`/`client_secret` Yandex и VK |

## Дизайн / motion

| ID | Нужно |
|---|---|
| `OWN-DESIGN-ACK` | Утвердить статику ключевых путей (после V04 draft pack) |
| `OWN-MOTION-ACK` | Утвердить конкретный motion «Рамка слота» |

## Право / деньги / пилот (не трогаем кодом)

| ID | Нужно |
|---|---|
| `OWN-LEGAL-GO` | Юрист/бухгалтер/реквизиты → legal publish |
| `OWN-PAY-PARTNER` | Письменная схема платежей/чеков |
| `OWN-PILOT` | Founding supply/demand pilot |

## Что уже не требует этих GO

- Локальные V0/V3/hold/calendar тесты в feature-ветке.  
- Локальный V07 viewport/keyboard/Lighthouse (формальный design DONE всё ещё ждёт motion ack).  
- DRAFT матрица V04 и Artist vNext storyboards в `docs/design/` без переноса в web.  
- AUTH stubs/Telegram/sessions локально (live Yandex/VK — только после OAuth secrets + staging).

## Не включать в этот packet

Повторные «нужен production», live payments, опасные prod-миграции, РКН/хостинг 152-ФЗ (`LEG-03`) — отдельные треки.
