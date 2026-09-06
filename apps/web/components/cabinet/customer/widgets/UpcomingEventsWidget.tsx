import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { DashboardWidget } from "../../DashboardWidget";
import type { CustomerEvent } from "../types";

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

export function UpcomingEventsWidget({ events }: { events: CustomerEvent[] }) {
  return (
    <DashboardWidget
      title="Ближайшие события"
      hint="Подтверждённые и активные даты"
      isEmpty={events.length === 0}
      empty="Нет запланированных событий — создайте заявку или откройте каталог."
    >
      <ul className="dashboard-list">
        {events.map((e) => (
          <li key={e.id}>
            <Link href={`/events/${e.id}`}>
              <strong>{e.title}</strong>
              <span className={`chip ${chipCls(e.status)}`}>{STATUS_LABEL[e.status] || e.status}</span>
              <span className="mono">
                {formatWhen(e.event_date)}
                {e.city ? ` · ${e.city}` : ""}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
