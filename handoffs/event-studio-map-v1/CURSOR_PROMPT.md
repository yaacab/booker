# Задание для Cursor

Интегрируй пакет `handoffs/event-studio-map-v1` в текущий проект «Букер» как новый Event Studio за feature flag `event_studio_map_v1`.

Обязательно:

1. Сначала прочитай корневой `AGENTS.md`, `docs/product/CONTRACT.md`, текущий маршрут `apps/web/app/events/new` и существующий API-клиент.
2. Не копируй mock-данные в production. Подключи реальные Event/Requirement/Profile/Venue/Availability endpoints.
3. Не вычисляй цену, комиссию, hold, возврат или гарант на клиенте. Окончательные суммы приходят только с сервера и связаны с `quote_id`.
4. Не удаляй старый сценарий до приёмки нового. Переключай реализации feature flag.
5. Сохрани два уровня: общий Event Control Room и отдельный Request/Deal Room для каждой позиции состава.
6. Реализуй доступность с состояниями `available`, `tentative`, `hold`, `busy`, `on_request`, временем последнего подтверждения и часовым поясом.
7. Добавь debounce-автосохранение, восстановление черновика, защиту от устаревшей версии и понятную ошибку повторной отправки.
8. На мобильном правая панель должна стать bottom sheet, а сводка — sticky CTA без перекрытия контента.
9. Проверь keyboard navigation, visible focus, aria-labels, контраст и `prefers-reduced-motion`.
10. Добавь unit/integration/E2E тесты по `INTEGRATION_CHECKLIST.md` и запусти typecheck/build.

Визуальная цель — `reference.webp`. Не стремись к пиксельной копии ценой архитектуры: сохрани простоту карты события, ясную иерархию и фирменную палитру «Букера».

Верни после работы:

- список изменённых файлов;
- описание API-связей;
- результаты тестов;
- скриншоты desktop и mobile;
- известные ограничения и безопасный rollback.
