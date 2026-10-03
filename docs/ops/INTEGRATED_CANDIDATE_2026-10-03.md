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
