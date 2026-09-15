import { expect, test } from '@playwright/test';
import { API_BASE, getJson, injectSession, postJson, register } from './helpers';

type Plan = { code: string; version: number; monthly_price_rub: number; annual_price_rub: number; supplier_fee_bps: number; customer_fee_bps: number; features: Record<string, boolean | number> };
for (const width of [1440, 390]) {
  test(`Admin manages commercial access at ${width}px`, async ({ page, request }, testInfo) => {
    const user = await register(request, `commercial-console-${width}-${Date.now()}@booker.test`, 'Тест коммерческого пульта');
    const org = await postJson<{ id: string }>(request, '/orgs', user.token, { name: `Пульт ${width} ${Date.now()}`, kind: 'artist' });
    await page.setViewportSize({ width, height: 900 });
    await injectSession(page, user.token, org.id);
    await page.goto('/admin/commerce');
    await expect(page.getByRole('alert').filter({ hasText: 'Только администратор платформы' })).toBeVisible();
    const admin = await postJson<{ token: string }>(request, '/auth/login', '', { email: 'admin@booker.test', password: 'password1' });
    await injectSession(page, admin.token, org.id);
    await page.goto('/admin/commerce');
    const revenue = page.getByRole('region', { name: 'Выручка и стоимость сделок' });
    await expect(revenue.getByRole('heading', { name: 'Платежи по сделкам', exact: true })).toBeVisible();
    await revenue.getByRole('heading', { name: 'Платежи по сделкам', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('commercial-revenue.png') });
    await revenue.getByLabel('Начало периода').fill('2020-01-01');
    await revenue.getByLabel('Конец периода').fill('2020-01-01');
    await revenue.getByRole('button', { name: 'Обновить отчёт' }).click();
    await expect(revenue.getByText('За выбранный период записей нет.', { exact: true })).toHaveCount(2);
    const campaigns = page.getByRole('region', { name: 'Кампании продвижения' });
    await campaigns.getByRole('combobox', { name: 'Статус кампании', exact: true }).selectOption('rejected');
    const campaignData = await getJson<{ total: number }>(request, '/admin/commerce/campaigns?state=rejected', admin.token);
    await expect(campaigns.getByText(`Найдено: ${campaignData.total}`, { exact: true })).toBeVisible();
    await page.getByLabel('Организация: название или ID').fill(org.id);
    await page.getByRole('button', { name: 'Найти организацию', exact: true }).click();
    await page.getByRole('button', { name: /^Управлять Пульт/ }).click();
    const form = page.getByRole('form', { name: 'Управление доступом', exact: true });
    await form.getByRole('combobox', { name: 'Тариф', exact: true }).selectOption('artist_pro');
    await form.getByLabel('Причина изменения доступа').fill('Проверка обращения поддержки');
    await form.getByRole('button', { name: 'Выдать ручной доступ' }).click();
    await expect(page.getByRole('status')).toContainText('Ручной доступ обновлён');
    const granted = await getJson<{ plan: { code: string } }>(request, `/commerce/organizations/${org.id}`, user.token);
    expect(granted.plan.code).toBe('artist_pro');
    await form.getByLabel('Причина изменения доступа').fill('Проверка поддержки завершена');
    await form.getByRole('button', { name: 'Отозвать доступ сейчас' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('commercial-access.png') });
    await form.getByRole('button', { name: 'Отозвать доступ сейчас' }).click();
    await expect(page.getByRole('status')).toContainText('Доступ отозван');
    const revoked = await getJson<{ plan: { code: string } }>(request, `/commerce/organizations/${org.id}`, user.token);
    expect(revoked.plan.code).toBe('artist_free');
    if (width === 1440) {
      const before = (await getJson<{ plans: Plan[] }>(request, '/admin/commerce/catalog', admin.token)).plans.find(p => p.code === 'artist_pro')!;
      try {
        await page.locator('details').filter({ hasText: 'Артисты · Pro' }).locator('summary').click();
        const priceForm = page.getByRole('form', { name: 'Цена artist_pro', exact: true });
        await priceForm.getByLabel('Цена за месяц, ₽').fill(String(before.monthly_price_rub + 10));
        await priceForm.getByLabel('Причина изменения цены').fill('Проверка новой версии цены');
        await priceForm.getByRole('button', { name: 'Сохранить новую цену' }).click();
        await expect(page.getByRole('status')).toContainText('Новая версия тарифа сохранена');
        const after = (await getJson<{ plans: Plan[] }>(request, '/commerce/catalog', user.token)).plans.find(p => p.code === 'artist_pro')!;
        expect(after.monthly_price_rub).toBe(before.monthly_price_rub + 10);
        expect(after.version).toBe(before.version + 1);
      } finally {
        const current = (await getJson<{ plans: Plan[] }>(request, '/admin/commerce/catalog', admin.token)).plans.find(p => p.code === 'artist_pro')!;
        if (current.version !== before.version) {
          const restored = await request.put(`${API_BASE}/admin/commerce/plans/artist_pro`, { headers: { Authorization: `Bearer ${admin.token}` }, data: {
            expected_version: current.version, monthly_price_rub: before.monthly_price_rub, annual_price_rub: before.annual_price_rub,
            supplier_fee_bps: before.supplier_fee_bps, customer_fee_bps: before.customer_fee_bps, features: before.features, reason: 'Возврат тестового каталога после E2E',
          } });
          expect(restored.ok()).toBe(true);
        }
      }
    }
  });
}
