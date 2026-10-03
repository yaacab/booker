# BK-INT-001 — интеграционный кандидат 03.10.2026

Основа: committed identity `5f06630` (включает support `989b51e`), плюс CI fixes PR19 `73dda35`, `d15be6a`; migration test paths `21a519c`. Незавершённый dirty Yandex не включён. Общий checkout не менялся.

## Локальные доказательства

- API: 812 PASS / 9 SKIP, 745.81s; `/tmp/booker-integrated-api-result.log`.
- Web build PASS; TypeScript PASS; source/build secret gate PASS.
- Полный браузерный прогон: 80 PASS / 7 FAIL / 1 SKIP. Две фикстуры импортировали API из неправильной папки; три Telegram теста не имели тестового bot token. Два таймаута на фоне одновременного полного API прогона; причина таймаутов не установлена.
- Исправлены пути импорта в двух операторских тестах и добавлен публичный fixture token в test-only CI job.
- Повтор затронутых пяти файлов на новой временной SQLite: 12 PASS (41.7s), включая contract/data-subject без изменения их кода. Лог `/tmp/booker-integrated-e2e-fix.log`.
- Финальные TypeScript, source secret gate и diff-check PASS.

## Открытые gates

Полный CI нового SHA, отдельный staff recovery browser, обзор интеграционного diff, настоящие Telegram/SMTP и staging/DB+uploads restore не подтверждены. Schema manifest manual_block; реальные деньги и production не включать. Фикстурный bot token не является реальным ботом. Дизайн-прототип отдельно ожидает владельца. Шкалы 59/56/15 без изменения.

## Telegram HMAC follow-up

При review обнаружено неверное исключение `signature` из bot-token HMAC. По https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app бот проверяет все поля кроме hash; исключение signature относится к отдельному Ed25519 flow. Исправлен набор подписанных полей. Регрессионный тест: до исправления 1 FAIL/9 PASS, после 10 PASS; дополнительно изменение/добавление неподписанного signature отклоняется. Profile API 26 PASS; browser Mini App с signature 5 PASS (8.8s); Ruff/diff/source secret gate PASS. Реальный Telegram WebView по-прежнему не проверен. Старый CI99 относится к fccf829 и не доказывает этот follow-up.

## CI99 fixture rate limit

CI99 fccf829: API/web/security/dependency checks SUCCESS; browser failed at support linked booking fixture with registration HTTP429. Fixture helper now respects numeric Retry-After 1..60 seconds with exactly one retry; persistent 429, invalid header and other errors still fail. Four controlled cases PASS; TypeScript/diff PASS. Server limiter unchanged. CI100 on 67ac8bd started before this fixture correction; new exact SHA needs CI.
