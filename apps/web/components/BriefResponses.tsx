"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
type Reply={id:string;message:string;supplier_name:string;artist_id?:string;status:string};
export function BriefResponses({briefId,date}:{briefId:string;date:string}) {
 const [rows,setRows]=useState<Reply[]|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 async function load(){setBusy(true);setError("");try{setRows((await api<{items:Reply[]}>(`/briefs/${briefId}/responses`)).items)}catch(e){setError(e instanceof Error?e.message:"Не удалось загрузить отклики")}finally{setBusy(false)}}
 return <div className="brief-responses"><button type="button" className="secondary" disabled={busy} onClick={()=>void load()}>{busy?"Загружаем…":rows?"Обновить отклики":"Посмотреть отклики"}</button>{error&&<p role="alert">{error}</p>}{rows?.length===0&&<p>Пока нет откликов. Заказ доступен артистам в поиске работы.</p>}{rows?.map(r=><article key={r.id} className="brief-response"><h3>{r.supplier_name}</h3><p>{r.message||"Артист заинтересован в вашем событии."}</p>{r.artist_id?<Link className="btn secondary" href={`/artists/${encodeURIComponent(r.artist_id)}?date=${date.slice(0,10)}`}>Профиль и запрос предложения →</Link>:<p>Артист ещё не добавил публичный профиль.</p>}</article>)}</div>;
}
export function BriefReply({briefId,orgId,alreadySent,closed,onSent}:{briefId:string;orgId:string;alreadySent:boolean;closed:boolean;onSent:()=>void}) {
 const [message,setMessage]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 async function send(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{await api(`/briefs/${briefId}/responses`,{method:"POST",body:JSON.stringify({supplier_org_id:orgId,message})});onSent()}catch(e){setError(e instanceof Error?e.message:"Не удалось отправить отклик")}finally{setBusy(false)}}
 if(alreadySent)return <p role="status" className="support-notice">Ваш отклик отправлен. Заказчик увидит его в своём заказе.</p>;
 if(closed)return <p className="timeline">Приём откликов завершён.</p>;
 return <details className="brief-reply"><summary>Откликнуться на заказ</summary><form onSubmit={send}><label>Ваше предложение<textarea rows={3} maxLength={4000} required value={message} onChange={e=>setMessage(e.target.value)} placeholder="Расскажите о программе, составе и опыте выступлений"/></label><p className="timeline">Отклик выражает интерес. Дата и окончательные условия согласуются отдельно.</p>{error&&<p role="alert">{error}</p>}<button disabled={busy}>{busy?"Отправляем…":"Отправить отклик"}</button></form></details>;
}
