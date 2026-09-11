"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { categoryLabel } from "@/lib/copy";
import { formatWhen, moscowDate, parseBookerDate } from "@/lib/format";
import { buildNextSteps, type RequirementLite, type EventRequestLite } from "@/lib/eventDayOps";
import { DashboardWidget } from "./DashboardWidget";

export type PlanningEvent = {id:string;title:string;city?:string;event_date:string;requirements?:RequirementLite[];requests?:EventRequestLite[]};

export function CustomerStaffingWidget({events,error}:{events:PlanningEvent[];error?:string}) {
  const needs=events.flatMap(event=>buildNextSteps(event.requirements||[],event.requests||[],r=>r.role_label||categoryLabel(r.category_code)).filter(step=>step.requirement.category_code!=="venue").map(step=>({event,step})));
  if(!needs.length&&!error)return null;
  return <DashboardWidget title="Кого ещё нужно найти" hint="Состав ближайших событий и заявки, которым нужен следующий шаг">
    {error&&<p role="status">{error}</p>}
    <ul className="dashboard-list">{needs.map(({event,step})=>{
      const search=new URLSearchParams({kind:"artist",category:step.requirement.category_code,event:event.id,date:moscowDate(event.event_date),city:event.city||"Москва"});
      if(step.requirement.id)search.set("requirement",step.requirement.id);
      const find=step.blocker==="no_request";
      return <li key={`${event.id}-${step.requirement.id||step.label}`}><article className="cabinet-deal-card"><h3>{step.label}{step.openSlots>1?` · ещё ${step.openSlots}`:""}</h3><p>{event.title} · {formatWhen(event.event_date)}</p><p className="timeline">{find?"Подберите артиста на свободную позицию.":"Заявка отправлена. Проверьте ответы и договорённости."}</p><Link className="btn secondary" href={find?`/search?${search}`:`/events/${event.id}`}>{find?"Подобрать артиста":"Посмотреть заявки"} →</Link></article></li>;
    })}</ul>
  </DashboardWidget>;
}

type Job={id:string;title:string;city:string;role_needed:string;date_from:string;date_to:string};
export function ArtistOpportunities({artistId}:{artistId:string}) {
  const [jobs,setJobs]=useState<Job[]>([]),[error,setError]=useState("");
  useEffect(()=>{
    if(!artistId)return;
    let cancelled=false;
    void (async()=>{
      try{
        const profile=await api<{category:string;city:string}>(`/artists/${encodeURIComponent(artistId)}`);
        const query=new URLSearchParams({role_needed:profile.category,city:profile.city});
        const data=await api<{items:Job[]}>(`/briefs?${query}`);
        if(!cancelled){setJobs(data.items.filter(j=>parseBookerDate(j.date_to).getTime()>Date.now()).sort((a,b)=>parseBookerDate(a.date_from).getTime()-parseBookerDate(b.date_from).getTime()).slice(0,3));setError("");}
      }catch{if(!cancelled)setError("Не удалось обновить открытые заказы. Попробуйте открыть поиск работы.");}
    })();
    return()=>{cancelled=true};
  },[artistId]);
  if(!jobs.length&&!error)return null;
  return <DashboardWidget title="Подходящие открытые заказы" hint="По вашей специализации и городу. Доступность и условия согласуются отдельно.">
    {error&&<p role="status">{error}</p>}
    <ul className="dashboard-list">{jobs.map(job=><li key={job.id}><Link href={`/briefs?q=${encodeURIComponent(job.title)}`}><strong>{job.title}</strong><span>{job.city} · {formatWhen(job.date_from)}</span><span>Посмотреть заказ и откликнуться →</span></Link></li>)}</ul>
    <p><Link href="/briefs">Все открытые заказы →</Link></p>
  </DashboardWidget>;
}
