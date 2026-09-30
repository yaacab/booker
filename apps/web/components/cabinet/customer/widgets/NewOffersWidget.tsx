import { DealCard } from "../../DealCard";
import { DashboardWidget } from "../../DashboardWidget";
import type { CustomerDealRoom } from "../types";

export function NewOffersWidget({ offers }: { offers: CustomerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Новые предложения"
      hint="Артист ответил — посмотрите программу, дату и стоимость"
      isEmpty={offers.length === 0}
      empty="Нет предложений, ожидающих вашего подтверждения."
    >
      <ul className="dashboard-list">
        {offers.map((d) => (
          <li key={d.booking_id}>
            <DealCard deal={d} viewer="customer" />
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
