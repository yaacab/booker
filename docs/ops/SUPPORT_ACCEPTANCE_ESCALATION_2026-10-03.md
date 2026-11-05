# BK-SUP-ESC — срок принятия срочного обращения

Статус: локальная реализация проверена адресно; полный CI итогового SHA требуется. Без deploy и внешней отправки.

Решение владельца: 15 рабочих минут на принятие urgent/high; календарь ежедневно 10:00–22:00 Europe/Moscow. Срок первого ответа независим и не изменён.

Реализация: отдельный acceptance_escalated_at; migration b12f34e56a78 после a11f23e45f67; draft manifest 52 revisions/manual_block. Worker использует CAS state_version/accepted_at, назначает доступного администратора с подтверждённой почтой и TOTP, сохраняет аудит и внутреннее уведомление. Email только ставится в очередь при явно настроенном адресате/SMTP. Telegram не включён. Повторный запуск не дублирует эскалацию; reopen сбрасывает marker и начинает новый срок.

Staff API/UI показывают срок принятия и отдельную эскалацию, фильтр escalated_only учитывает оба основания. Клиентский ответ не раскрывает staff marker.

Проверки: адресные migration/acceptance 9 PASS; после исправления отсутствующего or_ проверка фильтра/reopen/CAS 4 PASS. Ruff PASS. Browser Playwright 1 PASS (390px, назначение/принятие/приватность). Полный API прогон выполняется: /tmp/booker-acceptance-full-api-final.log, session 77361; не считать CI/staging принятыми.

Исправленные дефекты в процессе: неподдерживаемый status escalated заменён назначением администратора без нового статуса; ожидаемый head в identity copy-upgrade обновлён; browser ожидает кнопку «Подтвердить принятие» для уже назначенного администратора.

Открытые gates: реальный scheduler, SMTP/Telegram доставка и адресаты, staging DB/restore, PG concurrency, CI точного итогового SHA. Локальный stale-CAS тест не является настоящим PG concurrency тестом. Проценты 59/56/15 без изменения.

Secret gate: source/build PASS. Deploy inventory in this developer clone reports exactly two dependency symlinks (apps/api/.venv, apps/web/node_modules); neither is tracked or intended for the release. Check a clean exported candidate before release; scanner exclusions were not weakened.

Clean payload verification PASS: /tmp/booker-acceptance-payload-bco7nb0k (HEAD archive plus scoped current changes, no dependency symlinks or generated screenshots). This is a local payload inspection, not a deployment.

Итог: полный API процесс, запущенный до исправления or_, завершился 818 PASS/9 SKIP/1 FAIL (NameError фильтра). Не считать этот прогон зелёным. На исправленном коде оба support escalation набора и deadline — 12 PASS; ранее migration/acceptance 9 PASS, browser 1 PASS. Полный прогон фиксированного коммита передаётся CI.
