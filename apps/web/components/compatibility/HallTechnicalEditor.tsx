"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { api, getActiveOrg, getToken } from "@/lib/api";
import { commerceError, type CommerceMe } from "@/lib/commerce";
import { SupplyCabinetNav } from "@/components/cabinet/SupplyCabinetNav";
import { loginHref } from "@/lib/next";

type Hall = { id: string; name: string; venue_name: string; venue_id: string };
type Facts = { capacity: number; stage_area_m2: number | null; power_kw: number | null; basic_sound: boolean | null; microphones: number | null; equipment: string[] | null; restrictions: string | null };
type Envelope = { version: number; data: Facts };
const numberFields = [["capacity", "Вместимость, гостей"], ["stage_area_m2", "Площадь сцены, м²"], ["power_kw", "Доступная мощность, кВт"], ["microphones", "Микрофоны, шт."]] as const;

function clearFlag(form: HTMLFormElement | null, name: string) {
  const input = form?.elements.namedItem(name); if (input instanceof HTMLInputElement) input.checked = false;
}

export function HallTechnicalEditor() {
  const [halls, setHalls] = useState<Hall[]>([]); const [hallId, setHallId] = useState(""); const [canManage, setCanManage] = useState(false);
  const [saved, setSaved] = useState<Envelope | null>(null); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setError("");
    void api<CommerceMe>("/me", { signal: controller.signal }).then(async (me) => {
      const org = me.organizations.find((o) => o.kind === "venue" && o.id === (getActiveOrg() || me.active_organization_id)) || me.organizations.find((o) => o.kind === "venue");
      if (!org) return;
      const result = await api<{ items: Hall[]; can_manage: boolean }>(`/organizations/${org.id}/technical-halls`, { signal: controller.signal });
      setHalls(result.items); setCanManage(result.can_manage); setHallId((id) => result.items.some((h) => h.id === id) ? id : result.items[0]?.id || "");
    }).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!hallId) return;
    const controller = new AbortController(); setSaved(null); setLoading(true); setError("");
    void api<Envelope>(`/halls/${hallId}/technical`, { signal: controller.signal }).then(setSaved).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [hallId, revision]);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!saved || busy || !canManage) return;
    const form = new FormData(e.currentTarget); const values = Object.fromEntries(numberFields.map(([key]) => [key, String(form.get(key) || "").trim() ? Number(form.get(key)) : null]));
    const equipment = String(form.get("equipment") || "").split("\n").map((s) => s.trim()).filter(Boolean);
    const restrictions = String(form.get("restrictions") || "").trim();
    const sound = form.get("basic_sound"); setBusy(true); setError(""); setNotice("");
    try { const result = await api<Envelope>(`/halls/${hallId}/technical`, { method: "PUT", body: JSON.stringify({ ...values, basic_sound: sound === "unknown" ? null : sound === "yes", equipment: form.get("no_equipment") ? [] : equipment.length ? equipment : null, restrictions: form.get("no_restrictions") ? "" : restrictions || null, expected_version: saved.version }) }); setSaved(result); setNotice("Параметры зала сохранены."); }
    catch(e) { setError(commerceError(e)); } finally { setBusy(false); }
  }
  const hall = halls.find((h) => h.id === hallId);
  return <main className="commerce-page"><p className="kicker">Кабинет площадки</p><h1>Техника залов</h1><SupplyCabinetNav mode="venue" /><p>Укажите фактическое оснащение. Пустые поля будут отмечены как неизвестные при проверке совместимости.</p>
    {error && <div className="card" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision((r) => r + 1)}>Загрузить актуальную версию</button><p className="timeline">Несохранённые изменения будут заменены.</p></div>}
    {loading && <p role="status">Загружаем параметры…</p>}{notice && <p role="status">{notice}</p>}
    {!loading && !getToken() && <Link className="btn" href={loginHref("/cabinet/venue/technical")}>Войти</Link>}
    {!loading && getToken() && !halls.length && !error && <p className="empty">Добавьте свой зал в <Link href="/cabinet/venue/calendar">календаре площадки</Link>.</p>}
    {halls.length > 0 && <label>Зал площадки<select value={hallId} onChange={(e) => { setNotice(""); setHallId(e.target.value); }}>{halls.map((h) => <option key={h.id} value={h.id}>{h.venue_name} · {h.name}</option>)}</select></label>}
    {saved && hall && <form key={`${hallId}-${saved.version}`} className="presentation-editor" aria-label="Оснащение зала" onSubmit={submit}>
      {!canManage && <p>У вас доступ только для просмотра.</p>}
      <fieldset disabled={busy || !canManage}><legend>{hall.name}</legend><div className="grid">{numberFields.map(([key, label]) => <label key={key}>{label}<input type="number" name={key} required={key === "capacity"} min={key === "capacity" ? 1 : 0} step={key === "power_kw" || key === "stage_area_m2" ? "0.1" : 1} defaultValue={saved.data[key] ?? ""} /></label>)}
        <label>Базовый звук<select name="basic_sound" defaultValue={saved.data.basic_sound === null ? "unknown" : saved.data.basic_sound ? "yes" : "no"}><option value="unknown">Неизвестно</option><option value="yes">Предоставляем</option><option value="no">Не предоставляем</option></select></label></div>
        <label>Оборудование — точные модели по одной на строке<textarea name="equipment" onInput={(e) => clearFlag(e.currentTarget.form, "no_equipment")} rows={4} defaultValue={saved.data.equipment?.join("\n") || ""} /></label>
        <label className="row"><input type="checkbox" name="no_equipment" defaultChecked={Array.isArray(saved.data.equipment) && !saved.data.equipment.length} />Дополнительное оборудование не предоставляем</label>
        <label>Ограничения площадки<textarea name="restrictions" onInput={(e) => clearFlag(e.currentTarget.form, "no_restrictions")} rows={4} maxLength={4000} defaultValue={saved.data.restrictions || ""} /></label>
        <label className="row"><input type="checkbox" name="no_restrictions" defaultChecked={saved.data.restrictions === ""} />Дополнительных ограничений нет</label>
      </fieldset>
      {canManage && <button type="submit" className="btn" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить параметры зала"}</button>}
      <Link className="btn secondary" href={`/compatibility?venue=${hall.venue_id}`}>Проверить совместимость с артистом</Link>
    </form>}
  </main>;
}
