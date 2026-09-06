import Link from "next/link";
import { HoldCountdown } from "@/components/HoldCountdown";
import { formatWhen } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerDealRoom } from "../types";

export function HoldsWidget({ holds }: { holds: PerformerDealRoom[] }) {
  return (
    <DashboardWidget
      title="Hold"
      hint="Даты удерживаются до оплаты"
      isEmpty={holds.length === 0}
      empty="Нет активных hold."
    >
      <ul className="dashboard-list">
        {holds.map((d) => (
          <li key={d.booking_id}>
            <Link href={`/deals/${d.booking_id}`}>
              <strong>{d.event_title}</strong>
              <span className="chip wait">Hold</span>
              {d.hold ? (
                <>
                  <HoldCountdown expiresAt={d.hold.expires_at} />
                  <span className="mono">до {formatWhen(d.hold.expires_at)}</span>
                </>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
