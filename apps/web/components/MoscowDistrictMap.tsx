"use client";
import {useEffect,useMemo,useState} from "react";
import geo from "@/lib/moscowDistrictGeometry.json";
export const moscowDistrictOptions=geo.districts.map(d=>({id:d.id,name:d.name}));
// Stable SVG attributes across Node and browser math implementations.
const project=(p:number[])=>[Number(p[0].toFixed(6)),Number((-Math.log(Math.tan(Math.PI/4+p[1]*Math.PI/360))*180/Math.PI).toFixed(6))];
export function MoscowDistrictMap({selected,onSelect,counts}:{selected:string;onSelect:(id:string)=>void;counts:Record<string,number>}){
 const [hovered,setHovered]=useState("");const [all,setAll]=useState(false);
 useEffect(()=>{const d=geo.districts.find(x=>x.id===selected);if(d&&(d.bounds[0]<37.29||d.bounds[1]<55.52||d.bounds[2]>37.91||d.bounds[3]>55.93))setAll(true)},[selected]);
 const current=geo.districts.find(d=>d.id===(hovered||selected));
 const paths=useMemo(()=>geo.districts.map(d=>({...d,path:d.rings.map(r=>r.map((p,i)=>`${i?"L":"M"}${project(p).join(",")}`).join(" ")+"Z").join(" ")})),[]);
 const bounds=all?[36.80,55.14,37.97,56.05]:[37.29,55.52,37.91,55.93];
 const a=project([bounds[0],bounds[3]]),b=project([bounds[2],bounds[1]]);
 const viewBox=[a[0],a[1],b[0]-a[0],b[1]-a[1]].join(" ");
 return <section className="district-map-panel" aria-label="Выбор района на карте Москвы"><div className="district-map-title"><div><p className="eyebrow">Москва по районам</p><h2>Выбери свою часть города</h2></div><button className="secondary" type="button" onClick={()=>setAll(x=>!x)}>{all?"Ближе к центру":"Вся Москва"}</button></div><div className="district-map-layout"><svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet" aria-label="Схема районов Москвы. Выберите район нажатием или в списке фильтров." onMouseLeave={()=>setHovered("")}>{paths.map(d=><path key={d.id} d={d.path} fillRule="evenodd" vectorEffect="non-scaling-stroke" className={[selected===d.id?"is-selected":"",hovered===d.id?"is-hovered":"",counts[d.id]?"has-venues":""].join(" ")} onMouseEnter={()=>setHovered(d.id)} onClick={()=>onSelect(selected===d.id?"":d.id)} data-district={d.id}><title>{`${d.name}: ${counts[d.id]||0} площадок`}</title></path>)}</svg><div className="district-map-info" aria-live="polite"><span className="map-info-label">{current?"Район":"Наведи на район"}</span><h3>{current?.name||"Где соберёмся?"}</h3><p>{current?`${counts[current.id]||0} площадок в подборке по текущим фильтрам.`:"Нажми на область карты, чтобы увидеть площадки в этом районе. На телефоне можно выбрать район в списке."}</p>{selected&&<button type="button" className="secondary" onClick={()=>onSelect("")}>Все районы</button>}<small>Контуры: <a href={geo.source} target="_blank" rel="noreferrer">© OpenStreetMap, ODbL</a><br/>Границы на 31.05.2026. Схема не показывает свободные даты.</small></div></div></section>
}
