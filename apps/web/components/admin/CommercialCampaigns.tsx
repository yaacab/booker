"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatWhen, money } from '@/lib/format';
const STATUS: Record<string, string> = { all: 'Все', draft: 'Черновик', pending_payment: 'Ожидает оплаты', scheduled: 'Запланирована', active: 'Активна', expired: 'Истекла', cancelled: 'Отменена', rejected: 'Отклонена' };
const ORDER_STATUS: Record<string, string> = { paid: 'Оплачен', pending_payment: 'Ожидает оплаты', created: 'Создан', cancelled: 'Отменён', failed: 'Не оплачен', refunded: 'Возвращён' };
type Campaign = { id: string; organization_name: string; product_code: string; status: string; ends_at: string; href: string; included_credit: boolean; requires_payment_review: boolean; order: { id: string; status: string; provider: string; amount_rub: number } | null };
export function CommercialCampaigns() {
  const [state, setState] = useState('all'); const [rows, setRows] = useState<Campaign[]>([]);
  const [offset, setOffset] = useState(0); const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load(start = 0, filter = state) {
    setBusy(true); setError('');
    try { const data = await api<{ items: Campaign[]; total: number }>(`/admin/commerce/campaigns?state=${filter}&offset=${start}&limit=25`); setRows(data.items); setTotal(data.total); setOffset(start); }
    catch(e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить кампании'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);
  return <section className="card" aria-label="Кампании продвижения">
    <h2>Кампании продвижения</h2>
    <label>Статус кампании<select value={state} disabled={busy} onChange={e => { setState(e.target.value); void load(0, e.target.value); }}>{Object.entries(STATUS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
    {error ? <p role="alert">{error}</p> : null}
    <p>Найдено: {total}</p>
    {!rows.length && !busy ? <p>Кампаний с выбранным статусом нет.</p> : null}
    <ul className="dashboard-list">{rows.map(c => <li key={c.id}>
      <strong>{c.organization_name} · {c.product_code}</strong><p>{STATUS[c.status]} · до {formatWhen(c.ends_at)}</p>
      <Link href={c.href}>Открыть профиль</Link>
      {c.order ? <p>Заказ {c.order.id} · {ORDER_STATUS[c.order.status] ?? c.order.status} · {money(c.order.amount_rub)} · {c.order.provider === 'stub' ? 'тест, без списания денег' : c.order.provider}</p> : <p>{c.included_credit ? 'Включённый Boost по тарифу' : 'Платёжное основание не найдено'}</p>}
      {c.requires_payment_review ? <p>Есть оплаченный заказ у остановленной кампании. Нужна проверка оператором; возврат не подтверждён.</p> : null}
    </li>)}</ul>
    <div className="actions"><button type="button" disabled={busy || offset === 0} onClick={() => void load(Math.max(0, offset-25))}>Предыдущие кампании</button><button type="button" disabled={busy || offset+25 >= total} onClick={() => void load(offset+25)}>Следующие кампании</button></div>
  </section>;
}
