import Link from "next/link";
import { formatWhen, parseBookerDate } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { DashboardWidget } from "../../DashboardWidget";
import { CabinetIcon } from "../../CabinetIcon";
import type { PerformerBooking } from "../types";

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

export function UpcomingPerformancesWidget({ bookings, title = "Ближайшие выступления" }: { bookings: PerformerBooking[]; title?: string }) {
  return <DashboardWidget title={title} isEmpty={bookings.length === 0} empty="Здесь появятся события с подтверждёнными и активными датами.">
    <ul className="dashboard-list workspace-event-list">
      {bookings.map(booking => {
        const date = booking.event_date ? parseBookerDate(booking.event_date) : null;
        return <li key={booking.id}><Link href={`/deals/${booking.id}`}>
          <span className="workspace-event-date"><strong>{date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("ru-RU", { day: "numeric", timeZone: "Europe/Moscow" }) : "—"}</strong><small>{date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("ru-RU", { month: "short", timeZone: "Europe/Moscow" }) : "Дата"}</small></span>
          <span className="workspace-event-copy"><strong>{booking.event_title}</strong>{booking.event_date ? <span><CabinetIcon name="clock" />{formatWhen(booking.event_date)}</span> : null}</span>
          <span className={`chip ${chipCls(booking.status)}`}>{STATUS_LABEL[booking.status] || booking.status}</span>
        </Link></li>;
      })}
    </ul>
  </DashboardWidget>;
}
