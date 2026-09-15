"use client";
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { money } from '@/lib/format';

type MoneyRow = { provider: string; status: string; source: string; product_kind?: string; count: number; amount_rub: number };
type Report = { period: { from: string; to: string }; as_of: string; notes: string[]; payments: MoneyRow[]; orders: MoneyRow[];
  booking_values: { kind: string; source: "recorded" | "test" | "mixed" | "unpaid"; bookings: number; gmv_known_rub: number; platform_fee_known_rub: number; missing_quotes: number; missing_fee_snapshots: number }[] };
const STATUS: Record<string, string> = { succeeded: 'Подтверждено API', paid: 'Оплачено', pending: 'Ожидает оплаты', pending_payment: 'Ожидает оплаты', created: 'Создано', refunded: 'Возвращено', partially_refunded: 'Частично возвращено', cancelled: 'Отменено', failed: 'Не оплачено' };
const SOURCE: Record<string, string> = { recorded: 'Внешний платёж', test: 'Тест · деньги не списывались', unverified: 'Провайдер не подтверждён' };
function Entries({ rows }: { rows: MoneyRow[] }) {
  if (!rows.length) return <p>За выбранный период записей нет.</p>;
  return <ul className="dashboard-list">{rows.map((r, i) => <li key={i}>
    <strong>{r.product_kind ? `${r.product_kind === 'subscription' ? 'Подписки' : r.product_kind === 'promotion' ? 'Продвижение' : r.product_kind} · ` : ''}{STATUS[r.status] ?? r.status}</strong>
    <p>{SOURCE[r.source]} · {r.provider}</p><p>{money(r.amount_rub)} · записей: {r.count}</p>
  </li>)}</ul>;
}
export function CommercialRevenue() {
  const [report, setReport] = useState<Report | null>(null);
  const [from, setFrom] = useState(''); const [to, setTo] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function load(initial = false) {
    setBusy(true); setError('');
    try {
      const query = !initial && from && to ? `?date_from=${from}&date_to=${to}` : '';
      const result = await api<Report>(`/admin/commerce/revenue${query}`);
      setReport(result); setFrom(result.period.from); setTo(result.period.to);
    } catch(e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить отчёт'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(true); }, []);
  return <section className="card" aria-label="Выручка и стоимость сделок">
    <h2>Выручка и стоимость сделок</h2>
    <p>Период по дате создания записи, московское время. Текущие статусы оплат показаны отдельно от стоимости сделок.</p>
    <form onSubmit={event => { event.preventDefault(); void load(); }}>
      <label>Начало периода<input type="date" value={from} required onChange={e => setFrom(e.target.value)} disabled={busy} /></label>
      <label>Конец периода<input type="date" value={to} required onChange={e => setTo(e.target.value)} disabled={busy} /></label>
      <button type="submit" disabled={busy}>Обновить отчёт</button>
    </form>
    {error ? <p role="alert">{error}</p> : null}
    {report ? <>
      <p>Данные за {report.period.from} — {report.period.to}. Состояние на {new Date(report.as_of).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} МСК.</p>
      <h3>Платежи по сделкам</h3><Entries rows={report.payments} />
      <h3>Заказы подписок и продвижения</h3><Entries rows={report.orders} />
      <h3>Начисленные и ожидаемые суммы</h3>
      {report.booking_values.map(v => <article className="card" key={`${v.kind}-${v.source}`}>
        <h4>{v.kind === 'accrued' ? 'Подтверждённые сделки · начислено' : 'Резервируемые сделки · ожидается'}</h4>
        <p>{{ recorded: 'Есть внешняя подтверждённая оплата', test: 'Тестовые бронирования', mixed: 'Есть внешние и тестовые оплаты — требуется проверка', unpaid: 'Без подтверждённой оплаты' }[v.source] ?? v.source}</p>
        <p>Бронирований: {v.bookings}</p><p>GMV, известный гонорар: {money(v.gmv_known_rub)}</p><p>Комиссия платформы, известная часть: {money(v.platform_fee_known_rub)}</p>
        {v.missing_quotes || v.missing_fee_snapshots ? <p>Неполные данные: без условий — {v.missing_quotes}, без полной комиссии — {v.missing_fee_snapshots}. Суммы не являются полным итогом.</p> : null}
      </article>)}
      <details><summary>Как читать отчёт</summary>{report.notes.map(note => <p key={note}>{note}</p>)}</details>
    </> : null}
  </section>;
}
