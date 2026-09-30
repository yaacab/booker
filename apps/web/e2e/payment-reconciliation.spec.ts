import { expect, test } from '@playwright/test';
import { injectSession, postJson } from './helpers';

for (const width of [1440, 390]) {
  test(`Operator payment reconciliation states at ${width}px`, async ({ page, request }, testInfo) => {
    const admin = await postJson<{ token: string }>(request, '/auth/login', '', { email: 'admin@booker.test', password: 'password1' });
    await injectSession(page, admin.token, '');
    await page.setViewportSize({ width, height: 900 });
    // Provider-response UI fixtures; API authorization and verified domain outcomes
    // are tested independently against SQLite and PostgreSQL, not replaced here.
    let result = 'error';
    await page.route('**/admin/payments/*/reconcile', async route => {
      if (result === 'error') await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Сверка статуса у этого партнёра пока недоступна' }) });
      else await route.fulfill({ json: { payment_id: 'fixture-payment', booking_id: 'fixture-booking', payment_status: 'succeeded', provider_status: 'succeeded', amount_rub: 106000, requires_operator: true, test_mode: true } });
    });
    await page.goto('/admin');
    const paymentSection = page.getByRole('button', { name: 'Внешняя оплата', exact: true });
    await paymentSection.click();
    await expect(paymentSection).toHaveAttribute('aria-pressed', 'true');
    const panel = page.getByRole('region', { name: 'Сверка платежа', exact: true });
    await expect(panel.getByText('Результат сверки появится здесь.', { exact: false })).toBeVisible();
    await panel.getByLabel('Идентификатор платежа для сверки').fill('fixture-payment');
    await panel.getByLabel('Код второго фактора для сверки').fill('123456');
    await panel.getByRole('button', { name: 'Сверить существующий платёж' }).click();
    await expect(panel.getByRole('alert')).toContainText('Сервис временно недоступен. Попробуйте ещё раз позже.');
    await expect(panel.getByLabel('Код второго фактора для сверки')).toHaveValue('');
    result = 'success';
    await panel.getByLabel('Код второго фактора для сверки').fill('654321');
    const submit = panel.getByRole('button', { name: 'Сверить существующий платёж' });
    await submit.focus(); await expect(submit).toBeFocused(); await submit.press('Enter');
    await expect(panel.getByRole('status')).toContainText('В Букере: Оплата подтверждена');
    await expect(panel.getByRole('status')).toContainText('Требуется сверка оператором');
    await expect(panel.getByRole('status')).toContainText('Тестовая проверка');
    await expect(panel.getByRole('link', { name: 'Открыть сделку после сверки' })).toHaveAttribute('href', '/deals/fixture-booking');
    await panel.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('payment-reconciliation.png') });
  });
}
