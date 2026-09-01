import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { DashboardWidget } from "../../DashboardWidget";
import type { CustomerEvent } from "../types";

export function DraftsWidget({ drafts }: { drafts: CustomerEvent[] }) {
  return (
    <DashboardWidget
      title="Черновики"
      hint="События без отправленных заявок"
      isEmpty={drafts.length === 0}
      empty="Черновиков нет — начните с Event Studio."
    >
      <ul className="dashboard-list">
        {drafts.map((e) => (
          <li key={e.id}>
            <Link href={`/events/${e.id}`}>
              <strong>{e.title}</strong>
              <span className="chip live">Черновик</span>
              <span className="mono">{formatWhen(e.event_date)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p style={{ marginTop: 12 }}>
        <Link className="btn secondary" href="/events/new">
          Новый черновик
        </Link>
      </p>
    </DashboardWidget>
  );
}
