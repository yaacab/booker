"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { api, getActiveOrg, getToken, isWriteRole } from "@/lib/api";
import { commerceError, type CommerceMe, type CommerceOrg } from "@/lib/commerce";
import { type ArtistPresentation, type PresentationEnvelope, type TechnicalRequirements } from "@/lib/presentation";
import { SupplyCabinetNav } from "@/components/cabinet/SupplyCabinetNav";
import { categoryLabel } from "@/lib/copy";
import { loginHref } from "@/lib/next";

const categories = ["dj", "host", "cover", "photo", "makeup", "decor", "catering"];
const numericTech = [["stage_area_m2", "Площадь сцены, м²"], ["power_kw", "Мощность, кВт"], ["microphones", "Микрофоны, шт."], ["setup_minutes", "Монтаж, минут"], ["teardown_minutes", "Демонтаж, минут"]] as const;
const lines = (value: FormDataEntryValue | null) => String(value || "").split("\n").map((s) => s.trim()).filter(Boolean);

export function PresentationEditor() {
  const [org, setOrg] = useState<CommerceOrg | null>(null);
  const [profiles, setProfiles] = useState<{ resource_id: string; label: string }[]>([]);
  const [artistId, setArtistId] = useState("");
  const [saved, setSaved] = useState<PresentationEnvelope | null>(null);
  const [data, setData] = useState<ArtistPresentation | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setError("");
    void api<CommerceMe>("/me", { signal: controller.signal }).then(async (me) => {
      const own = me.organizations.find((o) => o.kind === "artist" && o.id === (getActiveOrg() || me.active_organization_id)) || me.organizations.find((o) => o.kind === "artist") || null;
      setOrg(own); if (!own) return;
      const targets = await api<{ items: { resource_type: string; resource_id: string; label: string }[] }>(`/organizations/${own.id}/calendar-targets`, { signal: controller.signal });
      const artists = targets.items.filter((t) => t.resource_type === "artist"); setProfiles(artists);
      setArtistId((id) => artists.some((a) => a.resource_id === id) ? id : artists[0]?.resource_id || "");
    }).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!artistId) return;
    const controller = new AbortController(); setLoading(true); setSaved(null); setData(null); setError("");
    void api<PresentationEnvelope>(`/artists/${artistId}/presentation`, { signal: controller.signal }).then((result) => { setSaved(result); setData(result.data); })
      .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [artistId, revision]);
  function field<K extends keyof ArtistPresentation>(key: K, value: ArtistPresentation[K]) { setData((d) => d ? { ...d, [key]: value } : d); }
  function tech<K extends keyof TechnicalRequirements>(key: K, value: TechnicalRequirements[K]) { if (data) field("technical", { ...data.technical, [key]: value }); }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!data || !saved || busy || !org || !isWriteRole(org.role)) return;
    const form = new FormData(e.currentTarget);
    const body = { ...data, gallery: lines(form.get("gallery")), genres: lines(form.get("genres")), travel_cities: lines(form.get("travel_cities")),
      technical: { ...data.technical, required_equipment: form.get("required_equipment_none") ? [] : lines(form.get("required_equipment")).length ? lines(form.get("required_equipment")) : null, supplied_equipment: form.get("supplied_equipment_none") ? [] : lines(form.get("supplied_equipment")).length ? lines(form.get("supplied_equipment")) : null }, expected_version: saved.version };
    setBusy(true); setError(""); setNotice("");
    try { const result = await api<PresentationEnvelope>(`/artists/${artistId}/presentation`, { method: "PUT", body: JSON.stringify(body) }); setSaved(result); setData(result.data); setNotice("Публичная витрина сохранена."); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  return <main className="commerce-page"><p className="kicker">{org?.name || "Кабинет артиста"}</p><h1>Витрина и райдер</h1><SupplyCabinetNav mode="performer" />
    <p>Покажите выступление и условия работы. Эти сведения помогают выбрать артиста; окончательные условия согласуются в предложении.</p>
    {loading && <p role="status">Загружаем витрину…</p>}
    {error && <div role="alert" className="card"><p>{error}</p><button onClick={() => setRevision((r) => r + 1)}>Загрузить актуальную версию</button><p className="timeline">Перезагрузка заменит несохранённые изменения.</p></div>}
    {notice && <p role="status">{notice} <Link href={`/artists/${artistId}`}>Открыть публичный профиль</Link></p>}
    {!loading && !getToken() && <Link className="btn" href={loginHref("/cabinet/performer/presentation")}>Войти</Link>}
    {!loading && getToken() && !profiles.length && !error && <p className="empty">Сначала создайте профиль артиста в <Link href="/cabinet/performer/calendar">календаре</Link>.</p>}
    {profiles.length > 1 && <label>Профиль<select value={artistId} onChange={(e) => { setNotice(""); setArtistId(e.target.value); }}>{profiles.map((p) => <option value={p.resource_id} key={p.resource_id}>{p.label}</option>)}</select></label>}
    {data && saved && org && <form key={`${artistId}-${saved.version}`} onSubmit={submit} aria-label="Редактор витрины" className="presentation-editor">
      {!isWriteRole(org.role) && <p className="timeline">У вас доступ только для просмотра.</p>}
      <fieldset disabled={busy || !isWriteRole(org.role)}><legend>О выступлении</legend><div className="grid">
        <label>Имя на афише<input required maxLength={255} value={data.name} onChange={(e) => field("name", e.target.value)} /></label>
        <label>Город<input required maxLength={128} value={data.city} onChange={(e) => field("city", e.target.value)} /></label>
        <label>Категория<select value={data.category} onChange={(e) => field("category", e.target.value)}>{categories.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}</select></label>
        <label>Формат<input maxLength={300} placeholder="Акустический концерт" value={data.format} onChange={(e) => field("format", e.target.value)} /></label>
        <label>Состав<input maxLength={500} placeholder="Вокал, гитара, перкуссия" value={data.lineup} onChange={(e) => field("lineup", e.target.value)} /></label>
        <label>Длительность, минут<input type="number" min={1} max={1440} value={data.duration_minutes ?? ""} onChange={(e) => field("duration_minutes", e.target.value ? Number(e.target.value) : null)} /></label>
      </div><label>Программа<textarea rows={5} maxLength={4000} value={data.program} onChange={(e) => field("program", e.target.value)} /></label>
      <div className="grid"><label>Жанры — по одному на строке<textarea name="genres" rows={3} defaultValue={data.genres.join("\n")} /></label><label>Города выезда — по одному на строке<textarea name="travel_cities" rows={3} defaultValue={data.travel_cities.join("\n")} /><span className="timeline">До {saved.limits.travel_cities} городов. Условия и расходы согласуются отдельно.</span></label></div></fieldset>
      <fieldset disabled={busy || !isWriteRole(org.role)}><legend>Портфолио</legend><p className="timeline">Публичные HTTPS-ссылки. До {saved.limits.gallery} фотографий и {saved.limits.links} дополнительных записей. Существующие материалы сохраняются при смене тарифа.</p>
        <label>Обложка — ссылка на изображение<input type="url" value={data.cover_url} onChange={(e) => field("cover_url", e.target.value)} /></label>
        <label>Основное видео выступления<input type="url" value={data.primary_video_url} onChange={(e) => field("primary_video_url", e.target.value)} /></label>
        <label>Галерея — ссылки по одной на строке<textarea rows={4} name="gallery" defaultValue={data.gallery.join("\n")} /></label>
        <h3>Дополнительные видео и аудио</h3>
        {data.links.map((link, index) => <div className="card" key={index}><div className="grid">
          <label>Тип записи<select value={link.kind} onChange={(e) => field("links", data.links.map((l, i) => i === index ? { ...l, kind: e.target.value as "video" | "audio" } : l))}><option value="video">Видео</option><option value="audio">Аудио</option></select></label>
          <label>Название записи<input maxLength={128} value={link.label} onChange={(e) => field("links", data.links.map((l, i) => i === index ? { ...l, label: e.target.value } : l))} /></label>
          <label>Ссылка на запись<input type="url" required value={link.url} onChange={(e) => field("links", data.links.map((l, i) => i === index ? { ...l, url: e.target.value } : l))} /></label>
        </div><button type="button" className="secondary" onClick={() => field("links", data.links.filter((_, i) => i !== index))}>Убрать запись</button></div>)}
        <button type="button" className="secondary" disabled={data.links.length >= saved.limits.links} onClick={() => field("links", [...data.links, { kind: "video", label: "", url: "" }])}>Добавить запись</button>
        <label>Порядок блоков<select value={data.layout} onChange={(e) => field("layout", e.target.value as ArtistPresentation["layout"])}><option value="standard">Сначала программа</option><option value="gallery_first" disabled={!saved.limits.advanced_layout && data.layout !== "gallery_first"}>Сначала портфолио — расширенный тариф</option></select></label>
        <label className="row"><input type="checkbox" checked={data.media_rights_confirmed} onChange={(e) => field("media_rights_confirmed", e.target.checked)} />Подтверждаю право публиковать эти материалы</label>
      </fieldset>
      <fieldset disabled={busy || !isWriteRole(org.role)}><legend>Райдер</legend><label>Условия и технические требования<textarea rows={4} maxLength={4000} value={data.rider_text} onChange={(e) => field("rider_text", e.target.value)} /></label>
        <p className="timeline">Пустое поле означает «неизвестно», а не отсутствие требований.</p><div className="grid">
          {numericTech.map(([key, label]) => <label key={key}>{label}<input type="number" min={0} step={key === "stage_area_m2" || key === "power_kw" ? "0.1" : "1"} value={data.technical[key] ?? ""} onChange={(e) => tech(key, e.target.value ? Number(e.target.value) : null)} /></label>)}
          <label>Нужен звук площадки<select value={data.technical.basic_sound === null ? "unknown" : data.technical.basic_sound ? "yes" : "no"} onChange={(e) => tech("basic_sound", e.target.value === "unknown" ? null : e.target.value === "yes")}><option value="unknown">Неизвестно</option><option value="yes">Да</option><option value="no">Нет</option></select></label>
          <label>Что требуется от площадки<textarea name="required_equipment" rows={3} defaultValue={data.technical.required_equipment?.join("\n") || ""} /></label>
          <label>Что привозим с собой<textarea name="supplied_equipment" rows={3} defaultValue={data.technical.supplied_equipment?.join("\n") || ""} /></label>
        </div><label className="row"><input name="required_equipment_none" type="checkbox" defaultChecked={Array.isArray(data.technical.required_equipment) && !data.technical.required_equipment.length} />Дополнительное оборудование площадки не требуется</label>
        <label className="row"><input name="supplied_equipment_none" type="checkbox" defaultChecked={Array.isArray(data.technical.supplied_equipment) && !data.technical.supplied_equipment.length} />Своё оборудование не привозим</label></fieldset>
      {isWriteRole(org.role) && <button className="btn" disabled={busy} type="submit">{busy ? "Сохраняем…" : "Сохранить публичную витрину"}</button>}
      <Link className="btn secondary" href={`/artists/${artistId}`}>Открыть профиль</Link>
    </form>}
  </main>;
}
