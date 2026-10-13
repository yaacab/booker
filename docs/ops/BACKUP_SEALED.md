# Опциональные запечатанные резервные копии

Legacy `tar.gz` с manifest проверяет случайную порчу, но не устанавливает подлинность. Опциональный `BOOKER_BACKUP_FORMAT=sealed` создаёт `.bke`: потоковый AES-256-GCM с новым случайным nonce для каждого архива, аутентифицированным заголовком и идентификатором ключа. Распаковка и проверка manifest выполняются только **после** успешной проверки GCM tag. [Ограничение режима GCM](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/): расшифрованным байтам нельзя доверять до завершения аутентификации.

Это локально проверенный opt-in путь. Он не включает сам по себе хранение ключа, off-site, согласованный DB+uploads snapshot, PostgreSQL restore или production RTO.

## Подготовка и выпуск

Нужен отдельный Python-интерпретатор с пакетом `cryptography`; в текущем API `.venv` его нет. Без него sealed backup прекращается до создания снимка. Ключ — ровно 32 **случайных бинарных** байта, файл владельца backup-процесса с правами `0600` или строже, без symlink, вне backup-каталога и uploads. Пример для будущего защищённого окружения (путь и пользователь должны быть утверждены отдельно):

```bash
install -m 600 /dev/null /secure/booker-backup-key-v1
openssl rand -out /secure/booker-backup-key-v1 32
chmod 600 /secure/booker-backup-key-v1
BOOKER_BACKUP_FORMAT=sealed \
BOOKER_BACKUP_KEY_FILE=/secure/booker-backup-key-v1 \
BOOKER_BACKUP_CRYPTO_PYTHON=python3 \
bash infra/run-booker-backup.sh
```

`run-booker-backup.sh` проверяет ключ и пакет до опциональной остановки сервиса. `backup-booker.sh` создаёт открытый снимок DB/uploads в отдельном каталоге `0700` под `/tmp` (или `BOOKER_BACKUP_STAGING_PARENT`) **вне** `BOOKER_BACKUP_DIR`, потоково шифрует tar без дополнительного открытого tar-файла, проверяет tag и содержимое до атомарной публикации `.bke` с правами `0600`. Если staging parent вложен в backup dir, команда отказывает. При обычной ошибке временные данные удаляются; после `SIGKILL` или потери питания они могут остаться в приватном staging до следующего запуска и требуют проверки/очистки оператором. Следующий запуск удаляет только свои staging-каталоги старше 24 часов. Off-site задание должно копировать **только опубликованные `.bke`**, а не весь backup dir. Retention применяется и к legacy `.tar.gz`, и к `.bke`; dry-run показывает кандидатов.

## Проверка и восстановление

```bash
BOOKER_BACKUP_KEY_FILE=/secure/booker-backup-key-v1 \
BOOKER_BACKUP_CRYPTO_PYTHON=python3 \
BOOKER_BACKUP_REQUIRE_SEALED_RESTORE=1 \
bash infra/restore-drill.sh /path/booker-YYYYMMDD.bke /tmp/booker-restore-drill
```

Restore выбирает формат по содержимому, а не только расширению. `BOOKER_BACKUP_REQUIRE_SEALED_RESTORE=1` запрещает legacy tar.gz; без флага старые архивы остаются совместимыми, но не имеют криптографической подлинности. Неверный ключ, повреждённый заголовок/шифртекст/tag, усечение и неизвестный формат завершаются ошибкой до создания restore target. Дешифрованный tar временно хранится в закрытом каталоге `/tmp`, проверяется после tag и удаляется после drill. После `SIGKILL`/потери питания каталог может остаться; следующий sealed restore удаляет свои каталоги старше 24 часов, а оператор должен проверить остатки после аварии. `BOOKER_BACKUP_MAX_RESTORE_BYTES` (по умолчанию 20 GiB) ограничивает размер архива и суммарный размер файлов в tar; также действует лимит 100 000 записей. Пределы надо подбирать по измеренным данным.

## Ротация и восстановимость

Создайте новый независимый 32-байтный ключ, переключите `BOOKER_BACKUP_KEY_FILE`, выполните новый backup и restore drill. Идентификаторы можно сверить командами `python3 infra/backup_crypto.py key-id /secure/booker-backup-key-v2` и `python3 infra/backup_crypto.py archive-key-id /path/archive.bke`. Старый ключ храните отдельно до истечения **всех** архивов, созданных им, и проверки нового цикла; утрата ключа делает старый архив невосстановимым. Не копируйте ключ вместе с архивом или uploads. Политика KMS, off-site и выдача доступа к ключам ещё не утверждены.

Локальный drill: `cd apps/api && .venv/bin/python -m pytest -q tests/test_backup_restore.py tests/test_backup_sealed.py`. Тест использует синтетическую SQLite и uploads, проверяет wrong key, tamper, rotation, permissions, legacy policy и retention. Это не staging/production restore.

## Evidence v2 для конкретного архива, 02.10.2026

Новый `backup-manifest.json` версии 2 содержит случайный archive ID, UTC время, тип снимка (`sqlite`/`postgresql`), revision из SQLite снимка либо `unknown` для PostgreSQL, ограниченный environment tag и состав uploads с SHA-256. После проверки tar и, для sealed, GCM tag, архив публикуется с fsync. Затем атомарно пишутся приватные `archive.evidence.json` и `.ops-backup.json`: SHA-256/размер уже опубликованного ciphertext (или legacy tar), hash manifest, ID, тип БД, encryption mode и публичный key ID без ключа. Содержимое БД, URL подключения и имена вложений наружу не выводятся.

`run-booker-ops-restore-drill.sh` выбирает sidecar указанного архива, сверяет hash/размер/тип БД, копирует архив в новый закрытый каталог `/tmp`, сверяет копию ещё раз и запускает SQLite drill только по копии. Итоговый `.ops-restore.json` включает тот же ID/hash, тип БД, revision, fingerprint набора вложений, version verifier и времена начала/окончания. Для PostgreSQL этот wrapper возвращает `UNKNOWN`: изолированный восстановительный verifier ещё не реализован. Старый archive/marker v1 может быть восстановлен прежним drill, но его evidence не считается зелёным. После ошибки публикации или evidence старые архивы не удаляются; уже опубликованный архив без marker оператор проверяет отдельно.
