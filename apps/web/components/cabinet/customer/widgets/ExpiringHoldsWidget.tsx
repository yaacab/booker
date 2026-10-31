import { DealCard } from "../../DealCard";
import { DashboardWidget } from "../../DashboardWidget";
import type { CustomerDealRoom } from "../types";

export function ExpiringHoldsWidget({ holds }: { holds: CustomerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Срок удержания заканчивается"
      hint="Проверьте договорённости до освобождения даты"
      isEmpty={holds.length === 0}
      empty="Нет удержаний, требующих внимания."
    >
      <ul className="dashboard-list">
        {holds.map((d) => (
          <li key={d.booking_id}>
            <DealCard deal={d} viewer="customer" />
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
