"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { CHIP, categoryLabel } from "@/lib/copy";
import { formatWhen, money, moscowDate } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { FavoriteToggle } from "@/components/FavoriteToggle";
import { PromoAttributionBeacon } from "@/components/promo/PromoAttributionBeacon";
import { SlotList } from "@/components/SlotList";

type Slot={id:string;starts_at:string;ends_at:string;status:string};
type Artist={id:string;name:string;city:string;category:string;verified?:boolean;media_url?:string|null;rider?:Record<string,string>;facts:{note:string;deals?:number;response?:string};tariffs:{id:string;title:string;honorarium_rub:number}[];slots:Slot[]};
type EventItem={id:string;title:string;status:string;event_date:string;city?:string};
type Requirement={id?:string;category_code:string;role_label?:string;qty?:number;notes?:string};
type QuickRequestResult={event_id?:string;request_id?:string;status?:string};
const CAT:Record<string,string>={dj:"DJ-сет",host:"Ведущий",cover:"Кавер"};
function requirementLabel(req:Requirement){const label=categoryLabel(req.category_code)||req.role_label||req.category_code;return req.qty&&req.qty>1?`${label} · ${req.qty} чел.`:label;}

export function ArtistProfileClient(){
 const params=useParams<{id:string}>(); const router=useRouter();
 const [data,setData]=useState<Artist|null>(null),[error,setError]=useState(""),[slotId,setSlotId]=useState(""),[busy,setBusy]=useState(false),[wantedDay,setWantedDay]=useState<string|null>(null),[signedIn,setSignedIn]=useState(false),[events,setEvents]=useState<EventItem[]>([]),[eventId,setEventId]=useState(""),[requirements,setRequirements]=useState<Requirement[]>([]),[requirementId,setRequirementId]=useState("");
 useEffect(()=>{const q=new URLSearchParams(window.location.search),wanted=q.get("slot"),day=q.get("date"),fromEvent=q.get("event"),fromReq=q.get("requirement");setWantedDay(day);if(fromEvent)setEventId(fromEvent);if(fromReq)setRequirementId(fromReq);fetch(`${process.env.NEXT_PUBLIC_API_URL||"/api"}/artists/${params.id}`).then(r=>r.ok?r.json():Promise.reject(new Error("Не найден"))).then((json:Artist)=>{setData(json);const live=json.slots.filter(s=>!s.ends_at||new Date(s.ends_at).getTime()>=Date.now());const open=live.find(s=>s.id===wanted&&s.status==="open")||(day?live.find(s=>s.status==="open"&&moscowDate(s.starts_at)===day):undefined)||live.find(s=>s.status==="open");if(open)setSlotId(open.id)}).catch((err:Error)=>setError(err.message));},[params.id]);
 useEffect(()=>{if(!getToken()){setSignedIn(false);setEvents([]);return}setSignedIn(true);let c=false;api<{items:EventItem[]}>("/events").then(r=>{if(!c)setEvents(r.items||[])}).catch(()=>{if(!c)setEvents([])});return()=>{c=true}},[]);
 useEffect(()=>{if(!eventId||!getToken()){setRequirements([]);return}let c=false;api<{requirements?:Requirement[]}>(`/events/${eventId}`).then(d=>{if(c)return;const items=d.requirements||[];setRequirements(items);setRequirementId(x=>x&&items.some(r=>r.id===x)?x:"")}).catch(()=>{if(!c)setRequirements([])});return()=>{c=true}},[eventId]);
 useEffect(()=>{if(data?.name)document.title=`${data.name} · Букер`},[data]);
 async function request(){if(!getToken()){const q=new URLSearchParams(window.location.search);if(slotId)q.set("slot",slotId);const qs=q.toString();router.push(loginHref(`/artists/${params.id}${qs?`?${qs}`:""}`));return}if(!slotId){setError("Нет свободного слота");return}const body:{artist_id:string;slot_id:string;event_id?:string;requirement_id?:string}={artist_id:params.id,slot_id:slotId};if(eventId){body.event_id=eventId;if(requirementId)body.requirement_id=requirementId}try{setBusy(true);const created=await api<QuickRequestResult>("/quick-request",{method:"POST",body:JSON.stringify(body)});const known=eventId||created.event_id;router.push(known?`/events/${encodeURIComponent(known)}`:"/cabinet")}catch(err){setError(err instanceof Error?err.message:"Ошибка заявки")}finally{setBusy(false)}}
 if(!data)return <main className="profile-v3"><h1>Профиль</h1><p>{error||""}</p>{!error?<div className="grid"><div className="skeleton"/><div className="skeleton"/><div className="skeleton"/></div>:null}</main>;
 const rider=data.rider||{},selectableRequirements=requirements.filter((r):r is Requirement&{id:string}=>Boolean(r.id));
 return <main className="profile-v3">
  <Suspense fallback={null}><PromoAttributionBeacon kind="artist" profileId={data.id}/></Suspense>
  <section className="profile-v3-hero">
   <div className="profile-v3-main"><p className="kicker">Профиль артиста</p><h1>{data.name}</h1><div className="profile-v3-meta"><span>{data.city}</span><span>·</span><span>{CAT[data.category]||data.category}</span>{data.verified?<span className="chip ok">{CHIP.verified}</span>:<span className="chip wait">{CHIP.pending}</span>}</div><p className="profile-v3-note">{data.facts.note}</p></div>
   <aside className="profile-v3-aside"><div><p className="kicker">Надёжность</p><h2>{data.facts.deals??0} сделок</h2><p className="timeline">Ответ обычно: {data.facts.response||"данных пока мало"}</p></div><div className="profile-v3-actions"><FavoriteToggle targetType="artist" targetId={data.id}/><Link className="btn secondary" href={`/artists/${data.id}/share`}>Поделиться</Link></div></aside>
  </section>
  <section className="profile-v3-grid"><article className="card"><h2>Формат и состав</h2><p>{rider.format||CAT[data.category]||"формат уточняется в Deal Room"}</p><p>{rider.lineup||"состав: уточняется"}</p></article><article className="card tint"><h2>Райдер</h2><p>{rider.tech||"Технический райдер согласуется после заявки. Это не цена."}</p></article><article className="card"><h2>Тарифы</h2><ul>{data.tariffs.map(t=><li key={t.id}>{t.title}: {money(t.honorarium_rub)}</li>)}</ul><p className="timeline">Ориентир. Итоговые условия приходят с сервера и связаны с quote_id.</p></article></section>
  <section className="profile-v3-booking"><h2>Выберите свободную дату</h2><SlotList slots={data.slots} value={slotId} onChange={setSlotId} selectable highlightDay={wantedDay}/>
   {!data.slots.some(s=>s.status==="open"&&(!s.ends_at||new Date(s.ends_at).getTime()>=Date.now()))?<p><a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Нет%20слота">Связаться с оператором</a></p>:null}
   {signedIn?<div className="grid" style={{marginTop:20}}><label>Событие<select value={eventId} onChange={e=>setEventId(e.target.value)} aria-label="Событие"><option value="">Новая заявка без события</option>{events.map(ev=><option key={ev.id} value={ev.id}>{ev.title}{ev.event_date?` · ${formatWhen(ev.event_date)}`:""}</option>)}</select></label>{eventId?<label>Роль<select value={requirementId} onChange={e=>setRequirementId(e.target.value)} aria-label="Роль в событии"><option value="">Без привязки к роли</option>{selectableRequirements.map(req=><option key={req.id} value={req.id}>{requirementLabel(req)}</option>)}</select></label>:null}</div>:null}
   {signedIn?<p className="timeline">Цена на этом шаге не считается. Предложение придёт с сервера.</p>:null}{error?<p style={{color:"var(--danger)"}}>{error}</p>:null}<p className="artist-desk-cta"><button type="button" onClick={()=>void request()} disabled={!slotId||busy}>{busy?"Отправляем заявку…":"Запросить предложение"}</button></p>
  </section><div className="sticky-cta"><button type="button" onClick={()=>void request()} disabled={!slotId||busy}>{busy?"Отправляем заявку…":"Запросить предложение"}</button></div>
 </main>;
}
