import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { CalendarConflict } from "../types";

export function CalendarConflictsWidget({ conflicts }: { conflicts: CalendarConflict[] }) {
  return (
    <DashboardWidget
      title="Конфликты календаря"
      hint="Пересечение дат в бронях — проверьте слоты"
      isEmpty={conflicts.length === 0}
      empty="Конфликтов календаря не обнаружено."
    >
      <ul className="dashboard-list">
        {conflicts.map((c) => (
          <li key={`${c.booking_id}-${c.conflict_booking_id}`}>
            <Link href={`/deals/${c.booking_id}`}>
              <strong>{c.event_title}</strong>
              <span className="chip bad">Конфликт</span>
              <span className="mono">
                {formatWhen(c.event_date)} · пересекается с «{c.conflict_with}»
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
