"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ProfileCompareButton } from "@/components/ProfileCompareButton";
import { api } from "@/lib/api";
import type { ArtistPresentation } from "@/lib/presentation";

function Photo({ url, alt, cover = false }: { url: string; alt: string; cover?: boolean }) {
  const [failed, setFailed] = useState(false);
  return failed ? <p className="timeline">Изображение временно недоступно</p> : <img className={cover ? "artist-cover" : "artist-gallery-photo"} src={url} alt={alt} loading={cover ? "eager" : "lazy"} referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}

export function ArtistCover({ data }: { data?: ArtistPresentation }) {
  return data?.cover_url ? <Photo key={data.cover_url} url={data.cover_url} alt={`Выступление ${data.name}`} cover /> : null;
}

export function ArtistShowcase({ data }: { data?: ArtistPresentation }) {
  if (!data) return null;
  const portfolio = <section className="card artist-portfolio" aria-label="Портфолио"><h2>Послушать и посмотреть</h2>
    {data.primary_video_url ? <p><a className="btn" href={data.primary_video_url} target="_blank" rel="noopener noreferrer">Посмотреть выступление ↗</a></p> : <p className="timeline">Основное видео пока не добавлено.</p>}
    {data.gallery.length > 0 && <div className="artist-gallery">{data.gallery.map((url, i) => <a href={url} target="_blank" rel="noopener noreferrer" key={`${url}-${i}`}><Photo url={url} alt={`${data.name} — фото ${i + 1}`} /></a>)}</div>}
    {data.links.length > 0 && <ul>{data.links.map((link, i) => <li key={i}><a href={link.url} target="_blank" rel="noopener noreferrer">{link.kind === "audio" ? "Аудио" : "Видео"}: {link.label || "Открыть запись"} ↗</a></li>)}</ul>}
  </section>;
  const program = <section className="card"><h2>Программа и география</h2><p className="preserve-lines">{data.program || "Программу можно уточнить перед предложением."}</p>
    {data.genres.length > 0 && <p>{data.genres.join(" · ")}</p>}
    <p>{data.duration_minutes ? `Продолжительность: ${data.duration_minutes} мин.` : "Продолжительность уточняется"}</p>
    <p>Базовый город: {data.city}. {data.travel_cities.length ? `Выезд: ${data.travel_cities.join(", ")}.` : "География выезда уточняется."}</p>
  </section>;
  return <div className="artist-showcase">{data.layout === "gallery_first" ? <>{portfolio}{program}</> : <>{program}{portfolio}</>}</div>;
}

export function ArtistTechnicalFacts({ data }: { data?: ArtistPresentation }) {
  const facts = data?.technical; if (!facts) return null;
  const rows: [string, string][] = [
    ["Сцена", facts.stage_area_m2 === null ? "Уточняется" : `${facts.stage_area_m2} м²`],
    ["Электропитание", facts.power_kw === null ? "Уточняется" : `${facts.power_kw} кВт`],
    ["Звук площадки", facts.basic_sound === null ? "Уточняется" : facts.basic_sound ? "Требуется" : "Не требуется"],
    ["Микрофоны", facts.microphones === null ? "Уточняется" : String(facts.microphones)],
    ["Монтаж", facts.setup_minutes === null ? "Уточняется" : `${facts.setup_minutes} мин.`],
    ["Демонтаж", facts.teardown_minutes === null ? "Уточняется" : `${facts.teardown_minutes} мин.`],
  ];
  return <dl className="technical-facts">{rows.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}<div><dt>От площадки</dt><dd>{facts.required_equipment === null ? "Уточняется" : facts.required_equipment.join(", ") || "Дополнительное оборудование не требуется"}</dd></div><div><dt>Привозим с собой</dt><dd>{facts.supplied_equipment === null ? "Уточняется" : facts.supplied_equipment.join(", ") || "Своё оборудование не привозим"}</dd></div></dl>;
}

type Reviews = { items: { id: string; rating: number; text: string; created_at: string }[]; average_rating?: number | null };
export function ArtistReviews({ artistId }: { artistId: string }) {
  const [data, setData] = useState<Reviews | null>(null); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => { const controller = new AbortController(); setError(false); setData(null); void api<Reviews>(`/artists/${artistId}/reviews`, { signal: controller.signal }).then(setData).catch(() => { if (!controller.signal.aborted) setError(true); }); return () => controller.abort(); }, [artistId, revision]);
  return <section className="card" aria-label="Отзывы"><h2>Отзывы после завершённых сделок</h2>
    {error ? <p role="alert">Отзывы временно недоступны. <button className="secondary" onClick={() => setRevision((r) => r + 1)}>Повторить</button></p> : !data ? <p role="status">Загружаем отзывы…</p> : <>
      {!data.items.length && <p className="timeline">Завершённых сделок с отзывами пока нет.</p>}
      {data.average_rating != null && <p>Средняя оценка: {data.average_rating} из 5</p>}
      {data.items.map((review) => <article key={review.id} className="artist-review"><p><strong>{review.rating} из 5</strong> · Заказчик · сделка завершена</p><p className="preserve-lines">{review.text || "Оценка без комментария"}</p></article>)}
    </>}
  </section>;
}

export function ArtistCompareButton({ artistId }: { artistId: string }) {
  return <ProfileCompareButton targetType="artist" targetId={artistId} />;
}
