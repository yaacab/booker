"use client";

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatWhen, money } from '@/lib/format';

type Refund = { id: string; payment_id: string; amount_rub: number; reason: string; provider: string; status: string; payment_status: string; created_at: string; test_mode: boolean; can_approve: boolean; can_retry: boolean; can_refresh: boolean; can_confirm_external: boolean };
const STATUS: Record<string, string> = { awaiting_approval: 'Ждёт второго администратора', approved: 'Подтверждён к исполнению', submitting: 'Запрос отправляется партнёру', pending: 'Ожидает подтверждения возврата', uncertain: 'Результат запроса пока неизвестен', succeeded: 'Возврат подтверждён', failed: 'Партнёр отклонил возврат', rejected: 'Запрос отклонён оператором' };
const PAYMENT: Record<string, string> = { succeeded: 'Оплата подтверждена', partially_refunded: 'Часть оплаты возвращена', refunded: 'Оплата возвращена полностью' };

export default function RefundsPage() {
  const [rows, setRows] = useState<Refund[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [totp, setTotp] = useState('');
  const [references, setReferences] = useState<Record<string, string>>({});
  const intent = useRef({ signature: '', key: '' });
  async function load(start = offset, state = filter) {
    const result = await api<{ items: Refund[]; has_more: boolean }>(`/admin/refunds?limit=25&offset=${start}${state ? `&status=${encodeURIComponent(state)}` : ''}`);
    setRows(result.items); setMore(result.has_more); setOffset(start);
  }
  async function refresh(start = offset, state = filter) {
    setBusy(true); setError('');
    try { await load(start, state); } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить возвраты'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void refresh(0); }, []);
  async function mutate(path: string, body: object) {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api<Refund>(path, { method: 'POST', body: JSON.stringify({ ...body, totp }) });
      setNotice(`${STATUS[result.status] || 'Статус уточняется'}${result.test_mode ? '. Тестовый возврат: деньги не перечислялись.' : '.'}`);
      await load(0);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сохранить действие'); }
    finally { setTotp(''); setBusy(false); }
  }
  return <main className="container" style={{ overflowWrap: 'anywhere' }}>
    <Link href="/admin">← Пульт оператора</Link>
    <h1>Возвраты платежей</h1>
    <p>Один администратор создаёт запрос, другой подтверждает его. Сумму и доступный остаток проверяет сервер. Принятый запрос ещё не означает перечисление денег.</p>
    {busy ? <p role="status">Загружаем данные…</p> : null}
    {error ? <div role="alert" className="card"><p>{error}</p><button disabled={busy} onClick={() => void refresh()}>Повторить загрузку</button></div> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <section className="card" aria-label="Подтверждение действий">
      <label>Код второго фактора<input value={totp} onChange={e => setTotp(e.target.value)} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} disabled={busy} /></label>
      <p>Введите свежий код перед каждым действием. Код не сохраняется.</p>
    </section>
    <form className="card" aria-label="Новый возврат" onSubmit={event => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      const request = { payment_id: String(form.get('payment')).trim(), amount_rub: form.get('amount') ? Number(form.get('amount')) : null, reason: String(form.get('reason')).trim() };
      const signature = JSON.stringify(request);
      if (intent.current.signature !== signature) intent.current = { signature, key: crypto.randomUUID() };
      void mutate('/admin/refunds', { ...request, idempotency_key: intent.current.key });
    }}>
      <h2>Новый запрос</h2>
      <label>Идентификатор платежа<input name="payment" required maxLength={36} disabled={busy} /></label>
      <label>Сумма возврата, ₽<input name="amount" type="number" min="1" step="1" disabled={busy} /></label>
      <p>Оставьте сумму пустой, чтобы запросить весь доступный остаток.</p>
      <label>Основание возврата<textarea name="reason" required minLength={3} maxLength={2000} disabled={busy} /></label>
      <button disabled={busy || totp.length !== 6}>Создать запрос возврата</button>
    </form>
    <section className="card" aria-label="Очередь возвратов">
      <h2>Запросы и результаты</h2>
      <label>Состояние<select value={filter} disabled={busy} onChange={e => { setFilter(e.target.value); void refresh(0, e.target.value); }}><option value="">Все состояния</option>{Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <button disabled={busy} onClick={() => void refresh()}>Обновить очередь</button>
      {!busy && !error && rows.length === 0 ? <p>Запросов возврата в этой выборке нет.</p> : null}
      <ul className="dashboard-list">{rows.map(row => <li key={row.id}>
        <article aria-label={`Возврат ${row.id}`}>
          <h3>{money(row.amount_rub)} · {STATUS[row.status] || 'Статус уточняется'}</h3>
          <p>{formatWhen(row.created_at)} · Платёж: {row.payment_id}</p>
          <p>{PAYMENT[row.payment_status] || 'Статус оплаты уточняется'}</p><p>{row.reason}</p>
          {row.test_mode ? <p>Тестовый возврат: деньги не перечисляются.</p> : null}
          {row.status === 'awaiting_approval' && !row.can_approve ? <p>Ожидается отдельное действие другого администратора.</p> : null}
          <div className="row">
            {row.can_approve ? <button disabled={busy || totp.length !== 6} onClick={() => void mutate(`/admin/refunds/${row.id}/approve`, {})}>Подтвердить и отправить возврат</button> : null}
            {row.status === 'awaiting_approval' ? <button className="secondary" disabled={busy || totp.length !== 6} onClick={() => void mutate(`/admin/refunds/${row.id}/reject`, {})}>Отклонить запрос</button> : null}
            {row.can_retry ? <button disabled={busy || totp.length !== 6} onClick={() => void mutate(`/admin/refunds/${row.id}/retry`, {})}>Повторить сохранённый запрос</button> : null}
            {row.can_refresh ? <button disabled={busy || totp.length !== 6} onClick={() => void mutate(`/admin/refunds/${row.id}/refresh`, {})}>Сверить статус с партнёром</button> : null}
          </div>
          {row.can_confirm_external ? <div>
            <p>Перевод вне платформы. Проверьте фактическое перечисление получателю перед подтверждением.</p>
            <label>Номер подтверждённого перевода<input value={references[row.id] || ''} onChange={e => setReferences({ ...references, [row.id]: e.target.value })} maxLength={255} disabled={busy} /></label>
            <button disabled={busy || totp.length !== 6 || (references[row.id] || '').trim().length < 3} onClick={() => void mutate(`/admin/refunds/${row.id}/confirm-external`, { transfer_reference: references[row.id] })}>Подтвердить фактический возврат вне платформы</button>
          </div> : null}
        </article>
      </li>)}</ul>
      <div className="row"><button disabled={busy || offset === 0} onClick={() => void refresh(Math.max(0, offset - 25))}>Предыдущие</button><button disabled={busy || !more} onClick={() => void refresh(offset + 25)}>Следующие</button></div>
    </section>
  </main>;
}
