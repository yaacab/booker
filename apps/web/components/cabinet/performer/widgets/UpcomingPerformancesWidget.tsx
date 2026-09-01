import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerBooking } from "../types";

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

export function UpcomingPerformancesWidget({ bookings }: { bookings: PerformerBooking[] }) {
  return (
    <DashboardWidget
      title="Ближайшие выступления"
      hint="Подтверждённые и активные даты"
      isEmpty={bookings.length === 0}
      empty="Нет запланированных выступлений."
    >
      <ul className="dashboard-list">
        {bookings.map((b) => (
          <li key={b.id}>
            <Link href={`/deals/${b.id}`}>
              <strong>{b.event_title}</strong>
              <span className={`chip ${chipCls(b.status)}`}>{STATUS_LABEL[b.status] || b.status}</span>
              {b.event_date ? <span className="mono">{formatWhen(b.event_date)}</span> : null}
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
