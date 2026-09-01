import { DashboardWidget } from "../../DashboardWidget";
import type { VenueHallTarget } from "../types";

export function VenueHallsWidget({ halls }: { halls: VenueHallTarget[] }) {
  return (
    <DashboardWidget
      title="Залы"
      hint="Календари площадки по залам"
      isEmpty={halls.length === 0}
      empty="Нет залов — добавьте зал в каталоге площадки."
    >
      <ul className="dashboard-list">
        {halls.map((h) => (
          <li key={h.resource_id}>
            <article className="dashboard-action-card">
              <strong>{h.label}</strong>
              <span className="chip live">{h.resource_type === "hall" ? "Зал" : h.resource_type}</span>
            </article>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
