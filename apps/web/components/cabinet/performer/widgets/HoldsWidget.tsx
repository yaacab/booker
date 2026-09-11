import { DealCard } from "../../DealCard";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function HoldsWidget({ holds }: { holds: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Даты удерживаются"
      hint="Проверьте срок и завершите согласование условий"
      isEmpty={holds.length === 0}
      empty="Сейчас нет удерживаемых дат."
    >
      <ul className="dashboard-list">
        {holds.map((d) => (
          <li key={d.booking_id}>
            <DealCard deal={d} viewer="supplier" />
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
