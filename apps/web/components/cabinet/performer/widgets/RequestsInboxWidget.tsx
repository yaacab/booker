import Link from "next/link";
import { formatWhen, money } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { DashboardWidget } from "../../DashboardWidget";
import type { PerformerRequest } from "../types";

function chipCls(status: string): string {
  if (status === "Confirmed" || status === "Completed") return "ok";
  if (status === "Dispute" || status === "Cancelled") return "bad";
  if (status === "DateHeld" || status === "AwaitingPayment") return "wait";
  return "live";
}

type RequestsInboxWidgetProps = {
  requests: PerformerRequest[];
  role: string;
  offerBusy: string | null;
  onSendOffer: (item: PerformerRequest) => void;
};

export function RequestsInboxWidget({ requests, role, offerBusy, onSendOffer }: RequestsInboxWidgetProps) {
  const sorted = [...requests].sort((a, b) => (b.event_date || "").localeCompare(a.event_date || ""));

  return (
    <DashboardWidget
      title="Все входящие"
      hint="Полный список заявок организации"
      accent="performer"
      span="full"
      isEmpty={sorted.length === 0}
      empty="Заявки появятся, когда заказчик отправит запрос на ваш свободный слот."
    >
      <ul className="dashboard-list" data-testid="performer-requests-inbox">
        {sorted.map((r) => {
          const pendingOffer = !r.offer_id && !r.booking_id;
          return (
            <li key={r.id}>
              <article className="dashboard-action-card">
                <strong>{r.event_title}</strong>
                <span className={`chip ${chipCls(r.status)}`}>{STATUS_LABEL[r.status] || r.status}</span>
                {r.event_date ? <span className="mono">{formatWhen(r.event_date)}</span> : null}
                <span className="timeline">витрина {money(r.honorarium_rub)}</span>
                {r.booking_id ? (
                  <Link className="btn" href={`/deals/${r.booking_id}`}>
                    Deal Room
                  </Link>
                ) : r.offer_id ? (
                  <span className="timeline">Предложение отправлено</span>
                ) : pendingOffer && role !== "viewer" ? (
                  <button type="button" disabled={offerBusy === r.id} onClick={() => onSendOffer(r)}>
                    {offerBusy === r.id ? "Отправляем…" : "Ответить предложением"}
                  </button>
                ) : pendingOffer ? (
                  <p className="timeline">Только просмотр</p>
                ) : null}
              </article>
            </li>
          );
        })}
      </ul>
    </DashboardWidget>
  );
}
