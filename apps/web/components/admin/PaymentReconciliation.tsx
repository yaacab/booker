"use client";

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { money } from '@/lib/format';

type Result = { payment_id: string; booking_id: string; payment_status: string; provider_status: string; amount_rub: number; requires_operator: boolean; test_mode: boolean };
const STATUS: Record<string, string> = { pending: 'Ожидает оплаты', succeeded: 'Оплата подтверждена', failed: 'Оплата не прошла', partially_refunded: 'Частично возвращено', refunded: 'Возвращено полностью' };
export function PaymentReconciliation() {
  const [paymentId, setPaymentId] = useState('');
  const [totp, setTotp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  return <section className="card" aria-label="Сверка платежа" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
    <h2>Сверка платежа с партнёром</h2>
    <p>Запросить состояние уже созданного платежа. Новый счёт и повторное списание не создаются. Сверка доступна и после истечения резерва.</p>
    <form aria-label="Запрос состояния платежа" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(''); setResult(null);
      try { setResult(await api<Result>(`/admin/payments/${encodeURIComponent(paymentId.trim())}/reconcile`, { method: 'POST', body: JSON.stringify({ totp }) })); }
      catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сверить статус'); }
      finally { setTotp(''); setBusy(false); }
    }}>
      <label>Идентификатор платежа для сверки<input value={paymentId} onChange={e => { setPaymentId(e.target.value); setResult(null); }} required maxLength={36} disabled={busy} /></label>
      <label>Код второго фактора для сверки<input value={totp} onChange={e => setTotp(e.target.value)} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required disabled={busy} /></label>
      <button disabled={busy || totp.length !== 6}>{busy ? 'Запрашиваем статус…' : 'Сверить существующий платёж'}</button>
    </form>
    {busy ? <p role="status">Ожидаем ответ партнёра…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {!result && !busy && !error ? <p>Результат сверки появится здесь. Переводы вне платформы проверяются оператором отдельно.</p> : null}
    {result ? <div role="status">
      <p>По данным партнёра: {STATUS[result.provider_status] || 'Статус уточняется'}.</p>
      <p>В Букере: {STATUS[result.payment_status] || 'Статус уточняется'} · {money(result.amount_rub)}.</p>
      {result.test_mode ? <p>Тестовая проверка: реальные деньги не списывались.</p> : null}
      {result.requires_operator ? <p>Требуется сверка оператором: оплата не подтверждает доступность даты или расходится с сохранённым состоянием. Проверьте сделку и необходимость возврата.</p> : null}
      <Link className="btn secondary" href={`/deals/${result.booking_id}`}>Открыть сделку после сверки</Link>
    </div> : null}
  </section>;
}
