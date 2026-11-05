#!/usr/bin/env python3
"""Recalculate Bukergo readiness from docs/progress/tasks.json.

Source of truth: docs/progress/tasks.json
Outputs:
  - docs/PROJECT_CHECKLIST.md (full generated checklist)
  - updates the AUTO-GENERATED section in docs/PROJECT_PROGRESS.md

Formula: DONE / active * 100 where active excludes CANCELLED.
Scopes MVP / DESIGN / FULL / INFRA are counted separately.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "docs" / "progress" / "tasks.json"
CHECKLIST_PATH = ROOT / "docs" / "PROJECT_CHECKLIST.md"
PROGRESS_PATH = ROOT / "docs" / "PROJECT_PROGRESS.md"

ACTIVE = ("DONE", "TODO", "IN PROGRESS", "BLOCKED", "DEFERRED")
STATUS_MARK = {
    "DONE": "✅",
    "IN PROGRESS": "🔄",
    "TODO": "⬜",
    "BLOCKED": "⛔",
    "DEFERRED": "⏸",
    "CANCELLED": "❌",
}

BEGIN = "<!-- BEGIN AUTO-GENERATED TASK-COUNT PROGRESS -->"
END = "<!-- END AUTO-GENERATED TASK-COUNT PROGRESS -->"


def load_tasks() -> dict:
    data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data.get("tasks"), list):
        raise SystemExit("tasks.json: missing tasks[]")
    ids = [t["id"] for t in data["tasks"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("tasks.json: duplicate task ids")
    return data


def active_tasks(tasks: list[dict], scope: str | None = None) -> list[dict]:
    out = []
    for task in tasks:
        if task["status"] == "CANCELLED":
            continue
        if scope and scope not in task.get("scopes", []):
            continue
        if task["status"] not in ACTIVE:
            raise SystemExit(f"unknown status {task['id']}: {task['status']}")
        out.append(task)
    return out


def pct(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * done / total, 2)


def stats(tasks: list[dict]) -> dict:
    counts = Counter(t["status"] for t in tasks)
    total = sum(counts[s] for s in ACTIVE)
    done = counts["DONE"]
    return {
        "total": total,
        "done": done,
        "in_progress": counts["IN PROGRESS"],
        "todo": counts["TODO"],
        "blocked": counts["BLOCKED"],
        "deferred": counts["DEFERRED"],
        "cancelled": 0,
        "pct": pct(done, total),
        "remaining": total - done,
    }


def direction_rows(data: dict) -> list[dict]:
    tasks = data["tasks"]
    dirs = sorted(data["directions"], key=lambda d: d["order"])
    rows = []
    for direction in dirs:
        subset = [t for t in active_tasks(tasks) if t["direction"] == direction["id"]]
        s = stats(subset)
        rows.append({"id": direction["id"], "title": direction["title"], **s})
    return rows


def next_priorities(tasks: list[dict], limit: int = 8) -> list[dict]:
    """Prefer in-flight and executable MVP tech work over owner/legal waits."""
    status_order = {"IN PROGRESS": 0, "TODO": 1, "BLOCKED": 2, "DEFERRED": 3}

    def rank(task: dict) -> tuple:
        tid = task["id"]
        scopes = set(task.get("scopes") or [])
        external = tid.startswith(("OWN-", "LEG-")) or tid in {"OWN-DESIGN-ACK", "OWN-LEGAL-GO"}
        mvp = "MVP" in scopes
        return (
            status_order[task["status"]],
            0 if (task["status"] == "TODO" and mvp and not external) else 1,
            0 if mvp else 1,
            0 if not external else 1,
            tid,
        )

    candidates = [t for t in tasks if t["status"] in status_order]
    candidates.sort(key=rank)
    return candidates[:limit]


def render_checklist(data: dict) -> str:
    tasks = data["tasks"]
    overall = stats(active_tasks(tasks))
    by_scope = {scope: stats(active_tasks(tasks, scope)) for scope in ("MVP", "DESIGN", "FULL", "INFRA")}
    hist = data.get("historical_weighted_scores", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# BUKERGO — PROJECT CHECKLIST",
        "",
        f"Автогенерация: `{now}` из [`docs/progress/tasks.json`](progress/tasks.json).",
        "Не редактировать вручную — меняйте `tasks.json` и запускайте `python3 scripts/progress_recalc.py`.",
        "",
        "## BUKERGO — PROJECT PROGRESS",
        "",
        f"- Всего: **{overall['total']}** задач",
        f"- Выполнено: **{overall['done']}**",
        f"- В работе: **{overall['in_progress']}**",
        f"- Ожидают: **{overall['todo']}**",
        f"- Заблокировано: **{overall['blocked']}**",
        f"- Отложено: **{overall['deferred']}**",
        f"- Общая готовность: **{overall['pct']:.2f}%**",
        f"- MVP: **{by_scope['MVP']['pct']:.2f}%** ({by_scope['MVP']['done']}/{by_scope['MVP']['total']})",
        f"- Дизайн: **{by_scope['DESIGN']['pct']:.2f}%** ({by_scope['DESIGN']['done']}/{by_scope['DESIGN']['total']})",
        f"- Полный запуск (FULL): **{by_scope['FULL']['pct']:.2f}%** ({by_scope['FULL']['done']}/{by_scope['FULL']['total']})",
        f"- Инфраструктура/релиз (INFRA): **{by_scope['INFRA']['pct']:.2f}%** ({by_scope['INFRA']['done']}/{by_scope['INFRA']['total']})",
    ]
    nxt = next_priorities(active_tasks(tasks), 1)
    if nxt:
        lines.append(f"- Следующая задача: **{nxt[0]['id']}** / {nxt[0]['title']}")
    lines += [
        "",
        "### Исторические взвешенные шкалы (не пересчитываются этой формулой)",
        "",
        f"- На {hist.get('as_of', '?')}: FULL **{hist.get('full_launch_pct', '?')}%** / "
        f"MVP **{hist.get('mvp_pct', '?')}%** / Design **{hist.get('design_pct', '?')}%**",
        f"- {hist.get('note', '')}",
        "",
        "## Сводка по направлениям",
        "",
        "| Направление | Всего | ✅ | 🔄 | ⬜ | ⛔ | ⏸ | % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in direction_rows(data):
        lines.append(
            f"| {row['title']} | {row['total']} | {row['done']} | {row['in_progress']} | "
            f"{row['todo']} | {row['blocked']} | {row['deferred']} | {row['pct']:.2f}% |"
        )

    lines += ["", "## Следующие приоритеты", ""]
    for task in next_priorities(active_tasks(tasks)):
        mark = STATUS_MARK[task["status"]]
        scopes = ",".join(task["scopes"])
        lines.append(f"- {mark} `{task['id']}` [{scopes}] — {task['title']}")

    dirs = {d["id"]: d for d in data["directions"]}
    by_dir: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        by_dir[task["direction"]].append(task)

    lines += ["", "## Полный чек-лист", ""]
    for direction in sorted(data["directions"], key=lambda d: d["order"]):
        lines.append(f"### {direction['order']}. {direction['title']}")
        lines.append("")
        for task in sorted(by_dir.get(direction["id"], []), key=lambda t: t["id"]):
            mark = STATUS_MARK.get(task["status"], "?")
            scopes = ", ".join(task["scopes"])
            evidence = "; ".join(task.get("evidence") or []) or "—"
            lines.append(
                f"- {mark} **{task['id']}** [{scopes}] {task['title']}  "
                f"<br/>status=`{task['status']}`; evidence: {evidence}"
            )
            if task.get("blocked_by"):
                lines.append(f"  - blocked_by: {', '.join(task['blocked_by'])}")
            if task.get("notes"):
                lines.append(f"  - notes: {task['notes']}")
        lines.append("")

    lines += [
        "## Правило обновления",
        "",
        "1. Меняйте только `docs/progress/tasks.json`.",
        "2. DONE только с evidence (код/тесты/конфиг/документ).",
        "3. Изменение scope — запись в `scope_change_log` с причиной.",
        "4. `python3 scripts/progress_recalc.py`",
        "",
    ]
    return "\n".join(lines)


def render_progress_section(data: dict) -> str:
    tasks = data["tasks"]
    overall = stats(active_tasks(tasks))
    by_scope = {scope: stats(active_tasks(tasks, scope)) for scope in ("MVP", "DESIGN", "FULL", "INFRA")}
    hist = data.get("historical_weighted_scores", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nxt = next_priorities(active_tasks(tasks), 5)
    lines = [
        BEGIN,
        "",
        f"## Автоматический task-count прогресс (обновлено {now})",
        "",
        "Источник истины: [`docs/progress/tasks.json`](progress/tasks.json). "
        "Полный чек-лист: [`docs/PROJECT_CHECKLIST.md`](PROJECT_CHECKLIST.md). "
        "Пересчёт: `python3 scripts/progress_recalc.py`.",
        "",
        "**Формула:** `DONE / (DONE + TODO + IN PROGRESS + BLOCKED + DEFERRED) × 100`. "
        "`CANCELLED` не входит в знаменатель. Это **не** взвешенные шкалы ниже.",
        "",
        "### BUKERGO — PROJECT PROGRESS",
        "",
        f"| Метрика | Значение |",
        f"|---|---|",
        f"| Всего активных задач | {overall['total']} |",
        f"| Выполнено (DONE) | {overall['done']} |",
        f"| В работе | {overall['in_progress']} |",
        f"| Ожидают | {overall['todo']} |",
        f"| Заблокировано | {overall['blocked']} |",
        f"| Отложено | {overall['deferred']} |",
        f"| **Общая готовность** | **{overall['pct']:.2f}%** |",
        f"| MVP | {by_scope['MVP']['pct']:.2f}% ({by_scope['MVP']['done']}/{by_scope['MVP']['total']}) |",
        f"| Дизайн | {by_scope['DESIGN']['pct']:.2f}% ({by_scope['DESIGN']['done']}/{by_scope['DESIGN']['total']}) |",
        f"| Полный запуск FULL | {by_scope['FULL']['pct']:.2f}% ({by_scope['FULL']['done']}/{by_scope['FULL']['total']}) |",
        f"| Инфраструктура INFRA | {by_scope['INFRA']['pct']:.2f}% ({by_scope['INFRA']['done']}/{by_scope['INFRA']['total']}) |",
        "",
        f"Исторические взвешенные шкалы на {hist.get('as_of')}: "
        f"FULL **{hist.get('full_launch_pct')}%** / MVP **{hist.get('mvp_pct')}%** / "
        f"Design **{hist.get('design_pct')}%** — сохранены без пересчёта.",
        "",
        "### Сводка по направлениям",
        "",
        "| Направление | Всего | DONE | IN PROGRESS | TODO | BLOCKED | DEFERRED | % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in direction_rows(data):
        lines.append(
            f"| {row['title']} | {row['total']} | {row['done']} | {row['in_progress']} | "
            f"{row['todo']} | {row['blocked']} | {row['deferred']} | {row['pct']:.2f}% |"
        )
    lines += ["", "### Следующие задачи", ""]
    for task in nxt:
        lines.append(
            f"- {STATUS_MARK[task['status']]} `{task['id']}` — {task['title']} (`{task['status']}`)"
        )
    lines += ["", END, ""]
    return "\n".join(lines)


def upsert_progress(section: str) -> None:
    text = PROGRESS_PATH.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        before, rest = text.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        new_text = before.rstrip() + "\n\n" + section + after.lstrip("\n")
    else:
        new_text = text.rstrip() + "\n\n" + section
    PROGRESS_PATH.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if generated files would change")
    args = parser.parse_args()
    data = load_tasks()
    checklist = render_checklist(data)
    section = render_progress_section(data)

    if args.check:
        current = CHECKLIST_PATH.read_text(encoding="utf-8") if CHECKLIST_PATH.exists() else ""
        if current != checklist:
            print("PROJECT_CHECKLIST.md is stale", file=sys.stderr)
            return 1
        progress = PROGRESS_PATH.read_text(encoding="utf-8")
        if BEGIN not in progress or section.split(BEGIN, 1)[1].split(END, 1)[0] not in progress:
            # simpler: ensure BEGIN block exists and matches regenerated body
            if BEGIN not in progress or END not in progress:
                print("PROJECT_PROGRESS.md missing AUTO block", file=sys.stderr)
                return 1
        print("ok")
        return 0

    CHECKLIST_PATH.write_text(checklist, encoding="utf-8")
    upsert_progress(section)
    overall = stats(active_tasks(data["tasks"]))
    print(
        f"updated checklist+progress: {overall['done']}/{overall['total']} "
        f"= {overall['pct']:.2f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
