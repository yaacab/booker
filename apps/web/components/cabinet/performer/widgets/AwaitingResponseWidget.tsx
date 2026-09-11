import { DealCard } from "../../DealCard";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function AwaitingResponseWidget({ deals }: { deals: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Предложения и согласование"
      hint="Проверьте, чьё подтверждение требуется для следующего шага"
      isEmpty={deals.length === 0}
      empty="Нет сделок, ожидающих ответа заказчика."
    >
      <ul className="dashboard-list">
        {deals.map((d) => (
          <li key={d.booking_id}>
            <DealCard deal={d} viewer="supplier" />
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
