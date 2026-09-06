# Delivery State

Updated: 2026-09-06

## Git

- Branch: `feat/master-plan-execution`
- Base HEAD for Spec v3 work: `c90d091`
- PR #14: open — **не merge** без OK владельца
- Prod deploy: **запрещён** в этой сессии

## Текущий стоп (честно)

- Cursor **Plan mode**; переключение в **Agent отклонено** пользователем.
- Код Wave 0–5 **не исполняется**. Параллельные агенты/worktree **не запущены**.
- Документы плана/gap/backlog обновлены уточнениями G1/G2, flag, payments, CI SHA, parallel ops.

## Docs готовы к выборочному коммиту (в Agent)

Только эти пути (не всё дерево):

- `docs/specs/`
- `docs/DELIVERY_GAP_ANALYSIS.md`
- `docs/DELIVERY_BACKLOG.md`
- `docs/DELIVERY_STATE.md`
- `docs/OWNER_INPUTS.md`
- `docs/product/CONTRACT.md`

Перед коммитом: `git diff` по списку; не `git add -A`.

## Следующее действие при Agent

1. Коммит docs (список выше).
2. Сразу W0-FLAG → W0-CI → W0-NAV/routes с тестами.
3. Параллельные worktree по независимым слотам после Wave 0.
4. Без «продолжать?» до исчерпания выполнимых A/B или честного списка блокеров.
5. Итог: G2 **только если A+B закрыты**, иначе список незакрытых критериев.

## Owner / env blockers (не замена G1)

См. `docs/OWNER_INPUTS.md`: PAYMENT_PARTNER, MAP_*, EMAIL/SMS, legal entity, LAWYER_APPROVAL.
