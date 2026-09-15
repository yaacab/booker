"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatWhen, money } from '@/lib/format';

type Plan = { code: string; title: string; audience: string; version: number; monthly_price_rub: number; annual_price_rub: number; supplier_fee_bps: number; customer_fee_bps: number; features: Record<string, boolean | number> };
type Subscription = { id: string; plan_code: string; status: string; provider: string; current_period_end: string; updated_at: string; cancel_at_period_end: boolean };
type Org = { id: string; name: string; kind: string; effective_status: string; subscription: Subscription | null };
const AUDIENCE: Record<string, string> = { artist: 'Артисты', venue: 'Площадки', customer: 'Заказчики' };
const STATUS: Record<string, string> = { free: 'Базовый доступ', active: 'Активна', trial: 'Пробный период', pending: 'Ожидает оплаты', past_due: 'Просрочен платёж', cancelled: 'Отменена', expired: 'Срок истёк' };

export default function CommercialAdmin() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [rows, setRows] = useState<Org[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const selected = rows.find(r => r.id === selectedId);

  async function organizations(start = 0) {
    const result = await api<{ items: Org[]; total: number }>(`/admin/commerce/organizations?q=${encodeURIComponent(query)}&offset=${start}&limit=25`);
    setRows(result.items); setTotal(result.total); setOffset(start);
  }
  async function load() {
    setError('');
    try {
      const catalog = await api<{ plans: Plan[] }>('/admin/commerce/catalog');
      setPlans(catalog.plans);
      await organizations(offset);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить данные'); }
  }
  useEffect(() => { setBusy(true); void load().finally(() => setBusy(false)); }, []);
  async function change(work: () => Promise<unknown>, message: string, refresh = true) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); if (refresh) await load(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : 'Изменение не сохранено'); }
    finally { setBusy(false); }
  }

  return <main className="wrap">
    <Link href="/admin">← Пульт оператора</Link>
    <h1>Коммерция</h1>
    <p>Тарифы и доступ организаций. Изменения сохраняются в журнале с указанием причины.</p>
    {error ? <div role="alert" className="card"><p>{error}</p><button type="button" disabled={busy} onClick={() => void load()}>Обновить данные</button></div> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <section className="card" aria-labelledby="admin-plans">
      <h2 id="admin-plans">Тарифы</h2>
      <p>Новая цена применяется к новым заказам. Суммы существующих заказов и предложений сохраняются.</p>
      {plans.map(plan => <details key={`${plan.code}-${plan.version}`} className="accordion">
        <summary>{AUDIENCE[plan.audience] ?? plan.audience} · {plan.title} · {money(plan.monthly_price_rub)}/мес</summary>
        <form aria-label={`Цена ${plan.code}`} onSubmit={event => {
          event.preventDefault(); const data = new FormData(event.currentTarget);
          void change(() => api(`/admin/commerce/plans/${plan.code}`, { method: 'PUT', body: JSON.stringify({ expected_version: plan.version,
            monthly_price_rub: Number(data.get('monthly')), annual_price_rub: Number(data.get('annual')), supplier_fee_bps: plan.supplier_fee_bps,
            customer_fee_bps: plan.customer_fee_bps, features: plan.features, reason: String(data.get('reason')) }) }), 'Новая версия тарифа сохранена.');
        }}>
          <p>Версия {plan.version}. Комиссия исполнителя {plan.supplier_fee_bps / 100}%, заказчика {plan.customer_fee_bps / 100}%.</p>
          <label>Цена за месяц, ₽<input name="monthly" type="number" min="0" max="10000000" step="1" defaultValue={plan.monthly_price_rub} required disabled={busy} /></label>
          <label>Цена за год, ₽<input name="annual" type="number" min="0" max="100000000" step="1" defaultValue={plan.annual_price_rub} required disabled={busy} /></label>
          <label>Причина изменения цены<textarea name="reason" minLength={3} maxLength={500} required disabled={busy} /></label>
          <button type="submit" disabled={busy}>Сохранить новую цену</button>
        </form>
      </details>)}
    </section>
    <section className="card" aria-labelledby="admin-subscriptions">
      <h2 id="admin-subscriptions">Подписки и ручной доступ</h2>
      <form onSubmit={event => { event.preventDefault(); void change(() => organizations(0), 'Список обновлён.', false); }}>
        <label>Организация: название или ID<input value={query} onChange={e => setQuery(e.target.value)} maxLength={128} /></label>
        <button type="submit" disabled={busy}>Найти организацию</button>
      </form>
      <p>Найдено: {total}</p>
      <ul className="dashboard-list">{rows.map(org => <li key={org.id}>
        <strong>{org.name}</strong> · {AUDIENCE[org.kind] ?? org.kind} · {STATUS[org.effective_status] ?? org.effective_status}
        <p className="mono">{org.id}</p>
        {org.subscription ? <p>{org.subscription.plan_code} · до {formatWhen(org.subscription.current_period_end)} · {org.subscription.provider === 'manual' ? 'Ручной доступ' : org.subscription.provider === 'stub' ? 'Тестовый платёж' : org.subscription.provider}{org.subscription.cancel_at_period_end ? ' · продление отключено' : ''}</p> : null}
        <button type="button" className="secondary" disabled={busy} onClick={() => setSelectedId(org.id)}>Управлять {org.name}</button>
      </li>)}</ul>
      <div className="actions"><button type="button" disabled={busy || offset === 0} onClick={() => void change(() => organizations(Math.max(0, offset-25)), 'Список обновлён.', false)}>Назад</button><button type="button" disabled={busy || offset+25 >= total} onClick={() => void change(() => organizations(offset+25), 'Список обновлён.', false)}>Далее</button></div>
      {selected ? <form key={`${selected.id}-${selected.subscription?.updated_at}`} aria-label="Управление доступом" onSubmit={event => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        void change(() => api(`/admin/commerce/organizations/${selected.id}/grant`, { method: 'POST', body: JSON.stringify({ plan_code: data.get('plan'), status: data.get('status'), days: Number(data.get('days')), reason: data.get('reason'), expected_updated_at: selected.subscription?.updated_at ?? '' }) }), 'Ручной доступ обновлён. Платёж не создавался.');
      }}>
        <h3>Доступ: {selected.name}</h3>
        <label>Тариф<select name="plan" defaultValue={selected.subscription?.plan_code ?? plans.find(p => p.audience === selected.kind)?.code} disabled={busy}>{plans.filter(p => p.audience === selected.kind).map(p => <option value={p.code} key={p.code}>{p.title}</option>)}</select></label>
        <label>Состояние<select name="status" defaultValue="trial" disabled={busy}><option value="trial">Пробный период</option><option value="active">Активна</option><option value="past_due">Просрочен платёж</option></select></label>
        <label>Дней доступа<input name="days" type="number" min="1" max="366" step="1" defaultValue="7" required disabled={busy} /></label>
        <label>Причина изменения доступа<textarea name="reason" minLength={3} maxLength={500} required disabled={busy} /></label>
        <p>Выдача нужна для поддержки и тестирования. Отзыв сразу отключает платные возможности, без возврата денег. Подписку с привязкой к автопродлению сначала обрабатывают у провайдера.</p>
        <button type="submit" disabled={busy}>Выдать ручной доступ</button>
        <button type="button" className="secondary" disabled={busy || !selected.subscription || ['cancelled', 'expired'].includes(selected.subscription.status)} onClick={event => {
          const form = event.currentTarget.form!; if (!form.reportValidity()) return;
          const data = new FormData(form);
          void change(() => api(`/admin/commerce/organizations/${selected.id}/revoke`, { method: 'POST', body: JSON.stringify({ expected_updated_at: selected.subscription!.updated_at, reason: data.get('reason') }) }), 'Доступ отозван. Денежные операции не изменены.');
        }}>Отозвать доступ сейчас</button>
      </form> : null}
    </section>
  </main>;
}
