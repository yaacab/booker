import Link from "next/link";
import { formatWhen, money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function ExpiringOffersWidget({ deals }: { deals: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Истекающие предложения"
      hint="Срок для согласования условий и удержания даты скоро закончится"
      isEmpty={deals.length === 0}
      empty="Нет предложений с истекающим сроком."
    >
      <ul className="dashboard-list">
        {deals.map((d) => (
          <li key={d.booking_id}>
            <Link href={`/deals/${d.booking_id}`}>
              <strong>{d.event_title}</strong>
              <span className="chip bad">Скоро истечёт</span>
              {d.quote.valid_until ? (
                <>
                  <span className="mono">до {formatWhen(d.quote.valid_until)} · {money(d.quote.total_rub)}</span>
                </>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
