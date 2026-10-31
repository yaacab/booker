import type { EventStudioDraft } from './types';
export interface VisualDraft {
 format:string|null; date:number|null; dateISO:string|null; time:string|null; endsAt?:string;
 city:string|null; guests:number|null; artists:string[]; venue:string|null;
 rider:{matches:number;open:number;requirements?:string[];notes?:string}|null;
 budget:number|null; artistsDeferred?:boolean; venueDeferred?:boolean;
}
const formats:Record<string,string>={private:'Частная вечеринка',wedding:'Свадьба',corporate:'Корпоратив',birthday:'День рождения',concert:'Концерт',other:'Другое'};
export function toVisual(d:EventStudioDraft):VisualDraft {
 const saved=d.assemblyV5;
 return {...saved,format:saved?saved.format:(d.title?Object.keys(formats).find(k=>formats[k]===d.kind)??'other':null),
 date:d.date?Number(d.date.slice(-2)):null,dateISO:d.date||null,time:d.startsAt||null,endsAt:d.endsAt,
 city:d.city||null,guests:saved?saved.guests:(d.title?d.guests:null),artists:[...d.talentIds],venue:d.venueId||null,
 rider:saved?.rider??null,budget:saved?.budget??null};
}
export function fromVisual(base:EventStudioDraft,v:VisualDraft):EventStudioDraft {
 const kind=formats[v.format||'']||base.kind;
 return {...base,kind,title:!base.title||base.title===base.kind?kind:base.title,city:v.city||base.city,date:v.dateISO||'',startsAt:v.time||base.startsAt,
 endsAt:v.endsAt||base.endsAt,guests:v.guests??base.guests,talentIds:[...v.artists],venueId:v.venue||undefined,
 requirements:v.rider?.requirements?[...v.rider.requirements]:base.requirements,
 assemblyV5:{...v,artists:[...v.artists]}};
}
