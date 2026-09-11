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

type NewRequestsWidgetProps = {
  requests: PerformerRequest[];
  role: string;
  offerBusy: string | null;
  onSendOffer: (item: PerformerRequest) => void;
};

export function NewRequestsWidget({ requests, role, offerBusy, onSendOffer }: NewRequestsWidgetProps) {
  return (
    <DashboardWidget
      title="Новые заявки"
      hint="Запросы, которые ждут вашего предложения"
      isEmpty={requests.length === 0}
      empty="Пока нет личных заявок. Найдите подходящий заказ в разделе «Подобрать выступления» и отправьте отклик."
    >
      <ul className="dashboard-list">
        {requests.map((r) => (
          <li key={r.id}>
            <article className="dashboard-action-card">
              <strong>{r.event_title}</strong>
              <span className={`chip ${chipCls(r.status)}`}>{STATUS_LABEL[r.status] || r.status}</span>
              {r.event_date ? <span className="mono">{formatWhen(r.event_date)}</span> : null}
              <span className="timeline">Стоимость в каталоге: {money(r.honorarium_rub)}</span>
              {r.booking_id ? (
                <Link className="btn" href={`/deals/${r.booking_id}`}>
                  Открыть договорённости
                </Link>
              ) : role === "viewer" ? (
                <p className="timeline">Только просмотр: предложение отправляет менеджер</p>
              ) : (
                <button type="button" disabled={offerBusy === r.id} onClick={() => onSendOffer(r)}>
                  {offerBusy === r.id ? "Отправляем…" : "Отправить предложение"}
                </button>
              )}
            </article>
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
