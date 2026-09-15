import { createHmac } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { API_BASE, injectSession, postJson, register } from './helpers';

function boundary(anchor: string, number: number) {
  const [year, month, day] = anchor.slice(0, 10).split('-').map(Number);
  const target = new Date(Date.UTC(year, month - 1 + number, 1));
  const end = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  return `${target.getUTCFullYear()}-${String(target.getUTCMonth() + 1).padStart(2, '0')}-${String(Math.min(day, end)).padStart(2, '0')}${anchor.slice(10)}`;
}

for (const width of [1440, 390]) {
  test(`Signed subscription periods and operator review at ${width}px`, async ({ page, request }, testInfo) => {
    const user = await register(request, `cycles-${width}-${Date.now()}@booker.test`, 'Периоды');
    const org = await postJson<{ id: string }>(request, '/orgs', user.token, { name: 'Студия периодов', kind: 'artist' });
    const original = await postJson<{ id: string; amount_rub: number; test_mode: boolean }>(request, `/commerce/organizations/${org.id}/orders`, user.token, { plan_code: 'artist_pro', billing_period: 'monthly', idempotency_key: 'initial-order' });
    expect(original.test_mode).toBe(true);
    await postJson(request, `/commerce/orders/${original.id}/test-complete`, user.token, { status: 'paid' });
    const response = await request.get(`${API_BASE}/commerce/orders/${original.id}`, { headers: { Authorization: `Bearer ${user.token}` } });
    const anchor = (await response.json()).period_start as string;
    async function cycle(number: number) {
      // Explicit local/CI stub acceptance protocol; these are never live charges.
      const body = JSON.stringify({ event_id: `${original.id}-cycle-${number}`, initial_order_id: original.id,
        subscription_reference: `sub:${original.id}`, reference: `${original.id}-payment-${number}`, cycle_number: number,
        period_start: boundary(anchor, number), period_end: boundary(anchor, number + 1), occurred_at: new Date().toISOString(),
        status: 'paid', amount_rub: original.amount_rub, currency: 'RUB' });
      const signature = createHmac('sha256', process.env.BOOKER_COMMERCE_WEBHOOK_SECRET || 'ci-test-only-commerce-webhook-secret').update(body).digest('hex');
      const result = await request.post(`${API_BASE}/commerce/renewal-webhook`, { data: body, headers: { 'X-Commerce-Signature': signature, 'Content-Type': 'application/json' } });
      expect(result.ok(), await result.text()).toBe(true);
      return result.json();
    }
    expect((await cycle(1)).requires_operator).toBe(false);
    await postJson(request, `/commerce/organizations/${org.id}/subscription/cancel`, user.token, {});
    expect((await cycle(2)).requires_operator).toBe(true);
    await injectSession(page, user.token, org.id);
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/cabinet/performer/growth');
    const history = page.getByRole('region', { name: 'Заказы и оплата' });
    await expect(history.getByText('Продление:', { exact: false })).toHaveCount(2);
    await expect(history.getByRole('status')).toContainText('Платёж требует сверки оператором');
    await expect(page.getByText('Автопродление отключено.', { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await history.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('subscription-periods.png') });
  });
}

for (const width of [1440, 390]) {
  test(`Late capture and refund of cancelled checkout at ${width}px`, async ({ page, request }) => {
    const user = await register(request, `late-capture-${width}-${Date.now()}@booker.test`, 'Поздняя оплата');
    const org = await postJson<{ id: string }>(request, '/orgs', user.token, { name: 'Студия', kind: 'artist' });
    const order = await postJson<{ id: string; amount_rub: number; test_mode: boolean }>(request, `/commerce/organizations/${org.id}/orders`, user.token, { plan_code: 'artist_pro', billing_period: 'monthly', idempotency_key: 'cancelled-order' });
    expect(order.test_mode).toBe(true);
    await postJson(request, `/commerce/orders/${order.id}/cancel`, user.token, {});
    async function deliver(status: 'paid' | 'refunded') {
      const body = JSON.stringify({ event_id: `${order.id}-${status}`, order_id: order.id, reference: `stub:${order.id}`, status, amount_rub: order.amount_rub, currency: 'RUB' });
      const signature = createHmac('sha256', process.env.BOOKER_COMMERCE_WEBHOOK_SECRET || 'ci-test-only-commerce-webhook-secret').update(body).digest('hex');
      const response = await request.post(`${API_BASE}/commerce/webhook`, { data: body, headers: { 'X-Commerce-Signature': signature, 'Content-Type': 'application/json' } });
      expect(response.ok(), await response.text()).toBe(true);
    }
    await deliver('paid');
    await injectSession(page, user.token, org.id);
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/cabinet/performer/growth');
    const current = page.getByRole('region', { name: 'Текущий тариф' });
    const history = page.getByRole('region', { name: 'Заказы и оплата' });
    await expect(current.getByRole('heading', { name: 'Free', exact: true })).toBeVisible();
    await expect(history.getByRole('status')).toContainText('Платёж требует сверки оператором');
    await deliver('refunded');
    await page.reload();
    await expect(history).toContainText('Возвращён');
    await expect(history.getByRole('status')).toHaveCount(0);
    await expect(current.getByRole('heading', { name: 'Free', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
