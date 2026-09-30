import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { API_BASE, getJson, injectSession, postJson, register, seedNegotiation } from './helpers';

const PYTHON = existsSync('../../.venv/bin/python') ? '../../.venv/bin/python' : 'python3';
function code() {
  return execFileSync(PYTHON, ['-c', "import pyotp; print(pyotp.TOTP('JBSWY3DPEHPK3PXP').now())"], { env: process.env }).toString().trim();
}
for (const width of [1440, 390]) {
  test(`Two operators refund a test payment at ${width}px`, async ({ page, request }, testInfo) => {
    if (process.env.BOOKER_ENVIRONMENT !== 'test' || !process.env.BOOKER_DATABASE_URL?.startsWith('sqlite:////tmp/')) throw new Error('Refund fixture requires disposable SQLite in /tmp and environment=test');
    const ctx = await seedNegotiation(request);
    for (const [side, actor] of [['customer', ctx.customer], ['supplier', ctx.owner]] as const) await postJson(request, `/offers/${ctx.offerId}/ack`, actor.token, { side });
    await postJson(request, `/bookings/${ctx.bookingId}/hold`, ctx.customer.token, {});
    const contract = await postJson<{ id: string }>(request, `/bookings/${ctx.bookingId}/contract`, ctx.customer.token, {});
    for (const [side, actor] of [['customer', ctx.customer], ['supplier', ctx.owner]] as const) {
      const inbox = await getJson<{ items: { entity_id: string; body: string }[] }>(request, '/notifications?limit=100', actor.token);
      const otp = inbox.items.find(n => n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0];
      expect(otp).toBeTruthy();
      await postJson(request, `/contracts/${contract.id}/sign`, actor.token, { side, otp });
    }
    const payment = await postJson<{ id: string }>(request, `/bookings/${ctx.bookingId}/payments`, ctx.customer.token, { idempotency_key: `refund-e2e-${ctx.bookingId}` });
    await postJson(request, `/payments/${payment.id}/stub-complete`, ctx.customer.token, {});
    const first = await register(request, `refund-first-${width}-${Date.now()}@booker.test`, 'Первый оператор');
    const second = await register(request, `refund-second-${width}-${Date.now()}@booker.test`, 'Второй оператор');
    execFileSync(PYTHON, ['-c', `
import sys
from booker_api.db import SessionLocal
from booker_api.models import User
with SessionLocal() as db:
    for user_id in sys.argv[1:]:
        user = db.get(User, user_id)
        user.is_platform_admin = True
        user.totp_enabled = True
        user.totp_secret = 'JBSWY3DPEHPK3PXP'
    db.commit()
`, first.user_id, second.user_id], { env: process.env });
    await page.setViewportSize({ width, height: 900 });
    await injectSession(page, first.token, ctx.customer.orgId);
    let fail = true;
    await page.route(`${API_BASE}/admin/refunds?**`, async route => {
      if (fail) { fail = false; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Очередь временно недоступна' }) }); }
      else await route.continue();
    });
    await page.goto('/admin/refunds');
    await expect(page.getByRole('alert').filter({ hasText: 'Очередь временно недоступна' })).toBeVisible();
    await page.getByRole('button', { name: 'Повторить загрузку' }).click();
    const form = page.getByRole('form', { name: 'Новый возврат' });
    await form.getByLabel('Идентификатор платежа').fill(payment.id);
    await form.getByLabel('Основание возврата').fill(`Возврат по согласованию ${ctx.bookingId}`);
    await page.getByLabel('Код второго фактора').fill(code());
    await form.getByRole('button', { name: 'Создать запрос возврата' }).click();
    await expect.poll(async () => (await getJson<{ items: { id: string }[] }>(request, `/admin/refunds?payment_id=${payment.id}`, first.token)).items.length).toBe(1);
    const rows = await getJson<{ items: { id: string }[] }>(request, `/admin/refunds?payment_id=${payment.id}`, first.token);
    const row = page.getByRole('article', { name: `Возврат ${rows.items[0].id}` });
    await expect(row).toContainText('Ожидается отдельное действие другого администратора');
    await expect(row.getByRole('button', { name: 'Подтвердить и отправить возврат' })).toHaveCount(0);
    await injectSession(page, second.token, ctx.customer.orgId);
    await page.goto('/admin/refunds');
    await page.getByLabel('Код второго фактора').fill(code());
    await row.getByRole('button', { name: 'Подтвердить и отправить возврат' }).click();
    await expect(row).toContainText('Оплата возвращена полностью');
    await expect(row).toContainText('Тестовый возврат: деньги не перечисляются');
    await row.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('refund-approved.png') });
    await page.getByRole('combobox', { name: 'Состояние', exact: true }).selectOption('uncertain');
    await expect(page.getByText('Запросов возврата в этой выборке нет.')).toBeVisible();
  });
}
