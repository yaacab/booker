import Link from "next/link";
import { HoldCountdown } from "@/components/HoldCountdown";
import { formatWhen, money } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function ExpiringOffersWidget({ deals }: { deals: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Истекающие предложения"
      hint="Hold скоро снимется — напомните заказчику"
      isEmpty={deals.length === 0}
      empty="Нет предложений с истекающим hold."
    >
      <ul className="dashboard-list">
        {deals.map((d) => (
          <li key={d.booking_id}>
            <Link href={`/deals/${d.booking_id}`}>
              <strong>{d.event_title}</strong>
              <span className="chip bad">Скоро истечёт</span>
              {d.hold ? (
                <>
                  <HoldCountdown expiresAt={d.hold.expires_at} />
                  <span className="mono">до {formatWhen(d.hold.expires_at)} · {money(d.quote.total_rub)}</span>
                </>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
