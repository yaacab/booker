import Link from "next/link";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { CustomerDealRoom } from "../types";

export function NewOffersWidget({ offers }: { offers: CustomerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Новые предложения"
      hint="Исполнитель отправил оффер — нужен ваш ack"
      isEmpty={offers.length === 0}
      empty="Нет предложений, ожидающих вашего подтверждения."
    >
      <ul className="dashboard-list">
        {offers.map((d) => (
          <li key={d.booking_id}>
            <Link href={`/deals/${d.booking_id}`}>
              <strong>{d.event_title}</strong>
              <span className="chip live">Нужен ack</span>
              <span className="mono">
                {money(d.quote.total_rub)} · quote {d.quote.quote_id.slice(0, 8)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
