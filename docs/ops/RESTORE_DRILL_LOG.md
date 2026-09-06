# Restore drill — журнал

Инструкция: прогон на **staging** (не затирать prod).

```bash
# 1) Взять свежий бэкап (cron / infra/backup-booker.sh)
# 2) Drill:
bash infra/restore-drill.sh /path/to/booker-backup-YYYYMMDD.tar.gz /tmp/booker-restore-drill
```

Скрипт распаковывает архив, проверяет наличие `booker.db` и читаемость таблицы `users`. При FAIL — не считать diligence ops закрытым.

## Записи

| Дата | Среда | Бэкап (имя/hash) | RTO факт | Результат | Кто | Заметки |
|------|-------|------------------|----------|-----------|-----|---------|
| _YYYY-MM-DD_ | staging | | _мин_ | PASS / FAIL | | |
| | | | | | | |

Шаблон строки: дата → путь к tar.gz → время до «db readable» → PASS только если `restore-drill.sh` exit 0.
