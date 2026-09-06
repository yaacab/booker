import Link from "next/link";
import { money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function AwaitingResponseWidget({ deals }: { deals: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Ожидающие ответа"
      hint="Оффер отправлен — ждём ack заказчика"
      isEmpty={deals.length === 0}
      empty="Нет сделок, ожидающих ответа заказчика."
    >
      <ul className="dashboard-list">
        {deals.map((d) => (
          <li key={d.booking_id}>
            <Link href={`/deals/${d.booking_id}`}>
              <strong>{d.event_title}</strong>
              <span className="chip wait">Ждём ack</span>
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
