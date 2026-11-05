# Аудит зависимостей — 02.10.2026

Срез локального незакоммиченного дерева на `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`. Источник: `npm audit` для `apps/web/package-lock.json`, `pip-audit` для установленного API окружения и двух закреплённых Python-графов. Аудит не подтверждает состояние VPS, staging или production.

| Пакет / уровень до исправления | Область и достижимость | Решение и риск |
|---|---|---|
| `next 15.5.23`, critical | Прямая runtime-зависимость. Image Optimization используется через `next/image`; AVIF-вектор нельзя исключить. Windows-hosted вектор для Linux VPS неприменим. | Lock обновлён до `15.5.27` (исправление AVIF в 15.5.24). Production build, web 11 unit, TypeScript, API 523 PASS / 4 SKIP и 3 локальных browser-сценария прошли; 1 сценарий юридического текста упал из-за отсутствующей фразы, не относящейся к зависимостям. Реальная обработка вредоносного AVIF и VPS не проверялись. |
| `sharp 0.34.5`, high | Опциональная runtime-зависимость Next для обработки изображений; путь потенциально достижим. | Lock обновлён до `0.35.5`. Нативные кодеки на VPS и вредоносные файлы не проверены. |
| `postcss 8.4.31`, high | Транзитивная зависимость Next; в проекте CSS поступает из исходников. Путь с контролируемым пользователем `sourceMappingURL` не найден, это вывод по текущему коду. | Override `8.5.23` из-за жёсткой зависимости Next 15.5.27 от старой версии. Сборка и web-сценарий служат проверкой совместимости; будущие обновления Next должны пересмотреть override. |
| `js-yaml 4.3.1`, high | Dev-зависимость ESLint, не web runtime. | Lock обновлён до `4.3.2`; риск dev-инструмента закрыт в текущем графе. |
| `brace-expansion 1.1.18 / 5.0.9`, high | Транзитивная dev-зависимость ESLint/minimatch; ввод из runtime приложения не проходит через неё. | Lock обновлён до `1.1.21 / 5.0.12`; риск dev-инструмента закрыт в текущем графе. |
| Python API, находок нет | Локально установленный граф из 38 пакетов, затем закреплённые runtime и dev графы. | Добавлены `apps/api/requirements-prod.lock` и `apps/api/requirements.lock`; оба `pip-audit` проходят. Новые CVE после даты проверки требуют нового скана. |

Начальный npm audit: **1 critical, 4 high** (5 пакетов). Повторный npm audit: **0** по всем уровням; Python audit: **0 известных** на момент проверки. У Python-файлов зафиксированы версии, но нет hash pinning; подмена артефакта реестра остаётся вне этого gate. Lock собран для Python 3.11 с версиями из локальной API `.venv` на Python 3.12; отдельная чистая локальная venv Python 3.11 установлена из lock, `uv pip check` проверил 39 пакетов; `pip-audit` установленного графа не нашёл известных уязвимостей (локальный `booker-api` не в PyPI и пропущен). Сам CI ещё не выполнен. Локально `uv pip compile` с закреплёнными constraints и сравнение `cmp` подтвердили полноту обоих lock относительно текущего `pyproject.toml`; CI повторяет эту проверку перед аудитом.

Политика: новая high/critical находка в runtime-библиотеке блокирует CI и релиз до обновления либо адресной проверки недостижимости. CI также блокирует high/critical в dev-графе через `npm audit --audit-level=high` и оба Python lock. Для исключения нужно отдельное ревью с advisory ID, затронутой версией, основанием, владельцем и датой истечения; после истечения исключение недействительно. Активных исключений нет. CI на PR и `main/master` запускает npm и Python audit до unit/build/E2E; scheduled smoke использует те же pinned версии. Локально подготовленный [release transaction](RELEASE_TRANSACTION_2026-10-02.md) создаёт отдельные venv из `requirements-prod.lock`, web `node_modules` и `.next` внутри нового каталога релиза; действующий каталог при подготовке не меняется. Fake-root тесты подтверждают восстановление предыдущего symlink/config при отказах API, web и nginx. На VPS этот путь, совместимость pinned графа с установленной ОС и фактический installed-graph audit не проверены; production выпуск остаётся закрыт до staging.

Повторить локально из корня репозитория:

```bash
cd apps/web && npm ci && npm audit --audit-level=high && npm run lint && npm run test:unit && npm run build
cd ../..
pip-audit -r apps/api/requirements-prod.lock --no-deps --disable-pip
pip-audit -r apps/api/requirements.lock --no-deps --disable-pip
python3 scripts/check_secret_exposure.py --source --deploy-payload --build
```

`pip-audit --no-deps` сканирует именно перечисленный pinned граф. CI сравнивает результат `uv pip compile` с lock, устанавливает версии из него и выполняет `pip check`; изменение `pyproject.toml` без обновления lock должно остановить CI. Никакого deploy, commit или push этим срезом не делалось.
