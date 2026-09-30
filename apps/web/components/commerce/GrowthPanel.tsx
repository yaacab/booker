"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, apiBase, getToken } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { money, formatDay } from "@/lib/format";

type Growth = {
  days: number; available_periods: number[]; profiles: { id: string; name: string }[];
  funnel: Record<string, number>; confirmed_honorarium_rub: number;
  response: { median_seconds: number | null; sample_size: number };
  conversions: { request_to_offer: number | null; request_to_confirmed: number | null };
  open_dates: string[]; suggestions: string[]; methodology: string; can_export: boolean;
  losses?: { reason: string; label: string; count: number }[];
  lost_requests?: { request_id: string; reason: string; label: string }[];
  benchmark: { status: string; message: string; cohort?: string; median_requests?: number };
};
const STEPS = [
  ["impressions", "Показы в каталоге"], ["profile_views", "Просмотры профиля"],
  ["favorites", "Добавления в избранное"], ["requests", "Заявки"], ["offers", "Предложения"],
  ["holds", "Удержания даты"], ["confirmed", "Подтверждено"], ["completed", "Завершено"],
] as const;
const percent = (value: number | null) => value === null ? "пока нет данных" : new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 1 }).format(value);

export function GrowthPanel({ orgId }: { orgId: string }) {
  const [data, setData] = useState<Growth | null>(null);
  const [days, setDays] = useState(30);
  const [profile, setProfile] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void api<Growth>(`/organizations/${orgId}/growth?days=${days}${profile ? `&target_id=${encodeURIComponent(profile)}` : ""}`, { signal: controller.signal })
      .then((result) => { setData(result); })
      .catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [orgId, days, profile, revision]);
  async function download() {
    setExporting(true); setError("");
    try {
      const response = await fetch(`${apiBase()}/organizations/${orgId}/growth/export?days=${days}${profile ? `&target_id=${encodeURIComponent(profile)}` : ""}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error("Не удалось выгрузить статистику. Проверьте тариф и повторите.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a"); a.href = url; a.download = "booker-growth.csv"; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(commerceError(e)); }
    finally { setExporting(false); }
  }
  return <section className="commerce-checkout" aria-label="Результаты и рост" aria-busy={loading}>
    <p className="kicker">От первого интереса до события</p><h2>Ваши результаты</h2>
    <div className="commerce-actions" role="group" aria-label="Период аналитики">{[7,30,90,365].map((period) =>
      <button className="btn secondary" type="button" key={period} aria-pressed={period === days} disabled={loading || (!!data && !data.available_periods.includes(period))} onClick={() => setDays(period)}>{period} дней</button>
    )}</div>
    {data && <label className="commerce-org">Профиль для аналитики<select value={profile} onChange={(e) => setProfile(e.target.value)}><option value="">Все мои профили</option>{data.profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
    {loading && <p role="status">Считаем результаты…</p>}
    {error && <div role="alert"><p>{error}</p><button className="btn secondary" onClick={() => { setDays(30); setRevision((r) => r + 1); }}>Повторить</button></div>}
    {data && !loading && !error && <>
      {data.profiles.length === 0 && <p className="empty">Создайте профиль и откройте свободные даты. Здесь появятся фактические результаты.</p>}
      <dl className="growth-metrics">{STEPS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{data.funnel[key]}</dd></div>)}</dl>
      <div className="card"><h3>Подтверждённые гонорары</h3><p className="commerce-price">{money(data.confirmed_honorarium_rub)}</p><p>Сумма условий подтверждённых сделок по заявкам периода. Это не сумма выплат.</p></div>
      <p>Заявка → предложение: <strong>{percent(data.conversions.request_to_offer)}</strong></p>
      <p>Заявка → подтверждение: <strong>{percent(data.conversions.request_to_confirmed)}</strong></p>
      <p>Медиана времени до первого предложения: <strong>{data.response.median_seconds === null ? "пока нет ответов" : `${Math.max(1, Math.round(data.response.median_seconds / 60))} мин`}</strong>{data.response.sample_size > 0 && ` · ответов в расчёте: ${data.response.sample_size}`}</p>
      <h3>Открытые даты на ближайший месяц</h3>
      {data.open_dates.length ? <p>{data.open_dates.map((date) => formatDay(`${date}T12:00:00Z`)).join(" · ")}</p> : <p>Открытых дат пока нет.</p>}
      {data.suggestions.length > 0 && <ul>{data.suggestions.map((hint) => <li key={hint}>{hint}</li>)}</ul>}
      <h3>Почему заявки закрылись</h3>
      {data.losses ? <>{data.losses.some((loss) => loss.count > 0) ? <ul>{data.losses.filter((loss) => loss.count > 0).map((loss) => <li key={loss.reason}>{loss.label}: <strong>{loss.count}</strong></li>)}</ul> : <p>Закрытых заявок за период нет.</p>}<p className="timeline">Причины показываются только по явным отметкам участников. Без отметки причина неизвестна.</p></> : <p>Подробные причины доступны в Pro и Premium. <Link href="/pricing">Сравнить тарифы</Link></p>}
      <h3>Похожие профили</h3><p>{data.benchmark.message}</p>
      {data.benchmark.status === "available" && <p>{data.benchmark.cohort}. Медиана заявок: <strong>{data.benchmark.median_requests}</strong>.</p>}
      {data.can_export && <button className="btn secondary" type="button" disabled={exporting} onClick={() => void download()}>{exporting ? "Готовим файл…" : "Экспорт статистики"}</button>}
      <details><summary>Как считаются результаты</summary><p>{data.methodology}</p></details>
    </>}
  </section>;
}
