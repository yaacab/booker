import Link from "next/link";
import { formatWhen, money } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";

export type CabinetDeal = {
  booking_id: string;
  event_title: string;
  event_date?: string | null;
  status: string;
  next_step?: string;
  action_required_from?: string[];
  participants?: {role:string;name:string;duty?:string}[];
  messages?: {id:string;kind:string;body:string;created_at?:string}[];
  quote: {quote_id:string;honorarium_rub:number;total_rub:number;customer_ack:boolean;supplier_ack:boolean};
  hold?: {status:string;expires_at:string} | null;
};

export function DealCard({deal,viewer}:{deal:CabinetDeal;viewer:"customer"|"supplier"}) {
  const owners=deal.action_required_from || [];
  const yours=owners.includes(viewer);
  const customer=deal.participants?.find(p=>p.role==="customer")?.name;
  const supplier=deal.participants?.find(p=>p.role==="supplier")?.name;
  const message=deal.messages?.filter(m=>m.kind!=="system").at(-1);
  const pending=owners.map(r=>r==="customer"?"заказчика":r==="supplier"?"артиста":"оператора").join(" и ");
  return <article className="cabinet-deal-card">
    <div className="cabinet-deal-heading"><h3>{deal.event_title}</h3><span className={`chip ${yours?"wait":"live"}`}>{STATUS_LABEL[deal.status]||deal.status}</span></div>
    {deal.event_date&&<p className="timeline">{formatWhen(deal.event_date)} · МСК</p>}
    {customer&&supplier&&<p className="cabinet-deal-parties">{customer} <span aria-hidden="true">↔</span> {supplier}</p>}
    <p><strong>{yours?"Нужен ваш ответ":pending?`Ждём ${pending}`:"Текущие договорённости"}</strong></p>
    {deal.next_step&&<p className="timeline">Следующий шаг: {deal.next_step.toLocaleLowerCase("ru")}.</p>}
    {deal.hold?.status==="active"&&<p className="cabinet-deal-deadline">Удержание до {formatWhen(deal.hold.expires_at)} · МСК</p>}
    <p className="mono">{viewer==="supplier"?`Гонорар: ${money(deal.quote.honorarium_rub)}`:`По предложению: ${money(deal.quote.total_rub)}`}</p>
    {message&&<blockquote className="cabinet-deal-message"><span>Последнее сообщение</span><p>{message.body}</p></blockquote>}
    <Link className={`btn ${yours?"":"secondary"}`} href={`/deals/${deal.booking_id}`}>{yours?deal.status==="Negotiation"?"Посмотреть предложение":deal.status==="AwaitingPayment"?"Посмотреть условия оплаты":"Перейти к согласованию":"Открыть договорённости"} →</Link>
  </article>;
}
