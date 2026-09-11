"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, getActiveOrg, getToken, setActiveOrg } from "@/lib/api";
import Link from "next/link";
import { BriefReply, BriefResponses } from "@/components/BriefResponses";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { formatWhen } from "@/lib/format";

type Brief = {
  id: string;
  organization_id: string;
  title: string;
  city: string;
  date_from: string;
  date_to: string;
  role_needed: string;
  guest_count_band: string;
  public_notes: string;
  status: string;
};

export default function BriefsPage() {
  const [items, setItems] = useState<Brief[]>([]);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [roleNeeded, setRoleNeeded] = useState("dj");
  const [city, setCity] = useState("Москва");
  const [band, setBand] = useState("51-100");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [published, setPublished] = useState(false);
  const [org,setOrg] = useState<{id:string;kind:string}|null>(null);
  const [sent,setSent] = useState<string[]>([]);
  const [history,setHistory] = useState<Brief[]>([]);
  const [categoryFilter,setCategoryFilter] = useState("");
  const [view,setView] = useState("all");
  const [accessReady,setAccessReady] = useState(false);
  const [started,setStarted] = useState(false);
  const [guideCity,setGuideCity] = useState("Москва");
  const [matchedCity,setMatchedCity] = useState("");

  async function load() {
    try {
      const data = await api<{ items: Brief[] }>("/briefs");
      setItems(data.items || []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить брифы");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const initialQuery=new URLSearchParams(window.location.search);
    setQuery(initialQuery.get("q")||"");
    setStarted(initialQuery.has("q")||initialQuery.has("category"));
    setCategoryFilter(initialQuery.get("category")||"");
    void load();
    if(!getToken()){setAccessReady(true);return;}
    let cancelled=false;
    api<{organizations:{id:string;kind:string}[];active_organization_id?:string}>("/me").then(async me=>{
      const id=getActiveOrg()||me.active_organization_id;
      const selected=me.organizations.find(o=>o.id===id)||me.organizations[0];
      if(cancelled||!selected)return;
      setOrg(selected);setActiveOrg(selected.id);
      if(selected.kind==="artist"||selected.kind==="venue"){
        const replies=await api<{items:{brief_id:string;brief:Brief}[]}>(`/brief-responses/mine?organization_id=${encodeURIComponent(selected.id)}`);
        if(!cancelled){setSent(replies.items.map(r=>r.brief_id));setHistory(replies.items.map(r=>r.brief));}
      }else if(selected.kind==="customer"){
        const own=await api<{items:Brief[]}>(`/briefs?status=all&organization_id=${encodeURIComponent(selected.id)}`);
        if(!cancelled)setHistory(own.items);
      }
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:"Не удалось загрузить кабинет")}).finally(()=>{if(!cancelled)setAccessReady(true)});
    return ()=>{cancelled=true};
  }, []);

  async function onPublish(e: FormEvent) {
    e.preventDefault();
    const org = getActiveOrg();
    if (!getToken() || !org) {
      setError("Нужен вход и активная организация заказчика");
      return;
    }
    const starts = new Date(`${dateFrom}:00+03:00`);
    const ends = new Date(`${dateTo}:00+03:00`);
    if (!Number.isFinite(starts.getTime()) || !Number.isFinite(ends.getTime()) || ends <= starts) {
      setError("Укажите начало и окончание события. Окончание должно быть позже начала.");
      return;
    }
    setBusy(true);
    setPublished(false);
    try {
      const created=await api<Brief>("/briefs", {
        method: "POST",
        body: JSON.stringify({
          organization_id: org,
          title,
          city,
          role_needed: roleNeeded,
          guest_count_band: band,
          public_notes: notes,
          date_from: starts.toISOString(),
          date_to: ends.toISOString(),
        }),
      });
      setHistory(rows=>[created,...rows]);
      setTitle("");
      setNotes("");
      setPublished(true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка публикации");
    } finally {
      setBusy(false);
    }
  }

  const source = view==="mine" ? Array.from(new Map([...items,...history].map(b=>[b.id,b])).values()) : items;
  const visible = source.filter((b) => (view!=="mine"||(org?.kind==="customer"?b.organization_id===org.id:sent.includes(b.id))) && (!matchedCity||b.city.toLocaleLowerCase("ru").includes(matchedCity.toLocaleLowerCase("ru"))) && (!categoryFilter||b.role_needed===categoryFilter) && `${b.title} ${b.city} ${categoryLabel(b.role_needed)}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));

  return (
    <main className="briefs-reference artist-guide-page">
      <header className="account-heading"><p className="kicker">Букер · артистам</p><h1>{org?.kind==="customer"?"Заказы и отклики артистов":"Ты артист? Давай подберём тебе варианты."}</h1><p>{org?.kind==="customer"?"Расскажите о событии и обсудите предложения артистов.":"Расскажи, чем занимаешься и где хочешь выступать. Посмотрим открытые предложения заказчиков."}</p></header>
      {accessReady&&org?.kind!=="customer"&&<section className="artist-guide" aria-labelledby="artist-guide-title"><div><p className="eyebrow">Начнём с тебя</p><h2 id="artist-guide-title">Какое выступление ищем?</h2><p>Подборка учитывает специализацию и город. Откликнуться можно из кабинета артиста.</p><ol className="artist-guide-steps"><li><span>01</span> Выбери направление</li><li><span>02</span> Посмотри предложения</li><li><span>03</span> Обсуди детали с заказчиком</li></ol></div><form onSubmit={e=>{e.preventDefault();setMatchedCity(guideCity.trim());setQuery("");setView("all");setStarted(true);requestAnimationFrame(()=>document.getElementById("artist-options")?.scrollIntoView({block:"start",behavior:"instant"}))}}><label>Твоё направление<select aria-label="Твоё направление" value={categoryFilter} onChange={e=>setCategoryFilter(e.target.value)}><option value="">Все направления</option>{Object.entries(CATEGORY).filter(([id])=>id!=="venue").map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><label>Город выступления<input value={guideCity} onChange={e=>setGuideCity(e.target.value)} placeholder="Например, Москва" required /></label><button type="submit">Подобрать варианты <span aria-hidden="true">↗</span></button></form></section>}
      {accessReady&&!started&&org?.kind!=="customer"&&<div className="artist-guide-next"><Link href={org?"/cabinet/performer":"/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer"}><strong>Пусть заказчики найдут тебя</strong><span>Добавь программу, фотографии и свободные даты в свой профиль. ↗</span></Link><Link href="/search?kind=venue"><strong>Присматриваешь место для выступления?</strong><span>Посмотри подборку площадок с фотографиями. Доступность уточняется. ↗</span></Link></div>}
      {org&&<div className="artist-first-actions" role="group" aria-label="Список заказов"><button aria-pressed={view==="all"} onClick={()=>{setView("all");setStarted(true)}}>Все заказы</button><button className="secondary" aria-pressed={view==="mine"} onClick={()=>{setView("mine");setStarted(true)}}>{org.kind==="customer"?"Мои заказы":"Мои отклики"}</button></div>}

      {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
      {published && <p role="status" className="support-notice">Заказ опубликован. Артисты могут отправлять отклики.</p>}
      {(started||org?.kind==="customer")&&<div className="briefs-columns" id="artist-options"><section className="briefs-results"><label className="brief-search">Найти заказ<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название, город или специалист" /></label>
      <label className="brief-search">Специализация<select value={categoryFilter} onChange={e=>setCategoryFilter(e.target.value)}><option value="">Все специализации</option>{Object.entries(CATEGORY).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
      <p className="timeline" role="status">{loading ? "Загружаем заказы…" : `Найдено: ${visible.length}`}</p>
      <ul className="brief-list">
        {visible.map((b) => <li key={b.id} className="card brief-card"><div className="brief-meta"><span className="chip">{categoryLabel(b.role_needed)}</span><span>{b.city}</span></div><h2>{b.title}</h2><p className="brief-dates">{formatWhen(b.date_from)} — {formatWhen(b.date_to)} · {b.guest_count_band} гостей · МСК</p>{b.public_notes && <p>{b.public_notes}</p>}<span className="timeline">{b.status === "open" ? "Открыт для предложений" : "Закрыт"}</span>
          {org?.id===b.organization_id?<BriefResponses briefId={b.id} date={b.date_from}/>:org?.kind==="artist"||org?.kind==="venue"?<BriefReply briefId={b.id} orgId={org.id} closed={b.status!=="open"} alreadySent={sent.includes(b.id)} onSent={()=>setSent(s=>[...s,b.id])}/>:accessReady&&!org&&b.status==="open"?<p><Link className="btn secondary" href="/login?mode=register&role=artist&next=%2Fbriefs">Войти как артист и откликнуться</Link></p>:null}
        </li>)}
      </ul>
      {!loading && !error && !visible.length && <div className="card"><h2>{view==="mine"?org?.kind==="customer"?"Вы ещё не публиковали заказы":"У вас пока нет откликов":"Пока нет предложений по этим условиям"}</h2><p>{view==="mine"&&org?.kind!=="customer"?"Откройте все заказы и выберите событие, на котором хотите выступить.":"Попробуйте другой город или направление. А пока можно заполнить профиль, чтобы заказчики могли пригласить вас сами."}</p>{org?.kind!=="customer"&&<Link className="btn secondary" href={org?"/cabinet/performer":"/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer"}>{org?"Дополнить профиль":"Создать профиль артиста"} ↗</Link>}</div>}
      </section>{org?.kind==="customer"?<details className="card brief-publish" open><summary>Опубликовать заказ</summary>
      <p className="timeline">Эти данные будут видны всем. Телефон, email и бюджет вашего частного события сюда не переносятся.</p>

      <form onSubmit={onPublish} className="brief-form">
        <label>Название события
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Заголовок"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        </label><label>Город
        <input
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Город"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        </label><label>Кого ищете
        <select value={roleNeeded} onChange={e=>setRoleNeeded(e.target.value)} required>{Object.entries(CATEGORY).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select>
        </label><label>Количество гостей
        <select
          className="rounded border border-black/15 px-3 py-2"
          value={band}
          onChange={(e) => setBand(e.target.value)}
        >
          <option value="1-50">1–50 гостей</option>
          <option value="51-100">51–100 гостей</option>
          <option value="101-200">101–200 гостей</option>
          <option value="200+">200+</option>
        </select>
        </label><label>Начало события (МСК)<input type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} required /></label>
        <label>Окончание события (МСК)<input type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} min={dateFrom || undefined} required /></label>
        <label>О событии
        <textarea
          className="rounded border border-black/15 px-3 py-2"
          placeholder="Публичные заметки"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="justify-self-start rounded bg-[#2D6A66] px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Публикация…" : "Опубликовать"}
        </button>
      </form>
      </details>:<aside className="card brief-publish"><h2>{"Покажи, что умеешь"}</h2><p>{"Программа, фотографии и свободные даты помогают заказчику выбрать тебя. Добавь их в профиль артиста."}</p><Link className="btn secondary" href={org?`/cabinet/${org.kind==="venue"?"venue":"performer"}`:"/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer"}>{org?"В мой кабинет":"Создать профиль артиста"}</Link></aside>}</div>}
    </main>
  );
}
