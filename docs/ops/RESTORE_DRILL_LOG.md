# Restore drill — журнал

Инструкция: прогон на **staging** (не затирать prod).

```bash
# 1) Взять свежий бэкап (cron / infra/backup-booker.sh)
# 2) Drill:
bash infra/restore-drill.sh /path/to/booker-backup-YYYYMMDD.tar.gz /tmp/booker-restore-drill
```

Скрипт проверяет состав архива и SHA-256 файлов по manifest, распаковывает SQLite в новый каталог `/tmp`, проверяет `PRAGMA integrity_check`, `foreign_key_check` и читаемость `users`. Manifest внутри legacy tar.gz не подтверждает подлинность: при замене архива его можно пересчитать. Для opt-in `.bke` сначала требуется ключ и проверка GCM tag; инструкция и ротация — [BACKUP_SEALED.md](BACKUP_SEALED.md). `BOOKER_BACKUP_REQUIRE_SEALED_RESTORE=1` отклоняет legacy. При FAIL — не считать diligence ops закрытым.

## Записи

| Дата | Среда | Бэкап (имя/hash) | RTO факт | Результат | Кто | Заметки |
|------|-------|------------------|----------|-----------|-----|---------|
| 2026-09-06 | prod VPS (isolated `/tmp`) | `booker-20260906T000539Z.tar.gz` | &lt;1 мин | PASS | agent | `infra/restore-drill.sh` exit 0; prod DB не трогали |
| 2026-10-01 | local isolated `/tmp/booker-local-drill-20261001` | `booker-20260930T224016Z.tar.gz`, SHA-256 `8a45acfc7713d41445033561ec471c0e712dc6fba2e61136fc1983a1cf3aca7a` | 0.05 с | PASS | Codex | Manifest/checksum и safe extract включены; Python создал online SQLite backup без `sqlite3` CLI; restore exit 0; `PRAGMA integrity_check=ok`, user/marker и upload совпали; production не затрагивался |
| 2026-10-01 | local synthetic `/tmp`, auto-cleaned | SHA-256 `b6c15b3f23a46b8b2222b5eabc2b370e94d5705076efbda1fe4545c6d06e1c3e` | не измерялся; backup+restore 0.284 с | PASS, только local SQLite | Codex | Повтор на финальном скрипте с атомарной публикацией: новый архив из искусственных `users`, `organizations`, `support_tickets`, `payments` и upload; manifest 2 файла, archive `0600`, backup/restore dirs `0700`; restored SQLite `integrity_check=ok`, значения и upload совпали. Отдельные тесты: tamper rejected, partial restore/backup cleanup, same-second archive uniqueness, retention dry-run/delete и service default. Не staging API recovery, не production RTO; временный каталог удалён. |
| 2026-10-02 | local synthetic pytest temp dirs, opt-in sealed | ephemeral `.bke`; ключ и архив удаляются pytest; hash не сохранялся | не измерялся; итоговый профильный suite 7.21 с, не RTO | PASS, только local SQLite | Codex | `test_backup_restore.py` + `test_backup_sealed.py`: **16 PASS** после ограничения архива, защищённого чтения ключа и выноса открытого staging из backup dir. Проверены DB/upload round-trip, режимы `0600`/`0700`, неверный ключ, изменение header/nonce/ciphertext/tag, усечение/дописание, ротация, legacy strict policy, retention, запрет staging внутри backup dir и fail-closed preflight. Полный API suite до последних защитных правок: **493 PASS, 4 SKIP**. PostgreSQL/staging/production restore, off-site и реальный RTO не проверены. |
| 2026-10-02 | local synthetic `/tmp` через pytest | новые `.tar.gz`/`.bke` и sidecar v2; файлы очищены pytest | RTO не измерялся | PASS только SQLite; PostgreSQL UNKNOWN | Codex | `test_backup_contract.py` + существующие backup/ops тесты: **32 PASS, 1 SKIP**. Проверены ID/hash/size, atomic evidence, старый архив после нового backup, tamper/wrong archive/key, revision и вложения, engine mismatch, legacy UNKNOWN, PG contract без PG restore. `TEST_POSTGRES_DSN` не задан; ни staging, ни production не проверены. |
| | | | | | | |

Шаблон строки: дата → путь к tar.gz → время до «db readable» → PASS только если `restore-drill.sh` exit 0.
