import { execFileSync } from 'node:child_process';
import { expect, test } from '@playwright/test';
import { getJson, injectSession, seedNegotiation } from './helpers';

for (const width of [1440, 390]) {
  test(`Expired proposal can be revised at ${width}px`, async ({ page, request }, testInfo) => {
    // Move only this fixture's quote deadline in the disposable local SQLite database.
    if (process.env.BOOKER_ENVIRONMENT !== 'test' || !process.env.BOOKER_DATABASE_URL?.startsWith('sqlite:////tmp/')) {
      throw new Error('Use BOOKER_ENVIRONMENT=test and a disposable BOOKER_DATABASE_URL=sqlite:////tmp/... for this clock fixture');
    }
    const ctx = await seedNegotiation(request);
    execFileSync('../../.venv/bin/python', ['-c', `
import sys
from datetime import timedelta
from booker_api.db import SessionLocal
from booker_api.models import Offer, OfferVersion
from booker_api.security import now
with SessionLocal() as db:
    offer = db.get(Offer, sys.argv[1])
    db.get(OfferVersion, offer.active_version_id).valid_until = now()-timedelta(seconds=1)
    db.commit()
`, ctx.offerId], { env: process.env });
    await page.setViewportSize({ width, height: 900 });
    await injectSession(page, ctx.owner.token, ctx.owner.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    await expect(page.getByRole('alert').filter({ hasText: 'Срок предложения истёк.' })).toBeVisible();
    if (width === 1440) await expect(page.getByRole('button', { name: 'Подтвердить условия', exact: true })).toBeDisabled();
    else await expect(page.getByRole('button', { name: 'Кивнуть условиям', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Перейти к новым условиям' }).click();
    await page.getByLabel('Новый гонорар, ₽').fill('97000');
    await page.getByLabel('Дополнительные условия').fill('Сет 2 часа, без изменения райдера');
    await page.getByLabel('Срок новых условий').selectOption('24');
    await page.getByRole('button', { name: 'Предложить новые условия' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('expired-offer-revision.png') });
    await page.getByRole('button', { name: 'Предложить новые условия' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Срок предложения истёк.' })).toHaveCount(0);
    const room = await getJson<{ can_ack_quote: boolean; quote: { quote_id: string; valid_until: string; honorarium_rub: number; terms: string; customer_ack: boolean; supplier_ack: boolean } }>(request, `/deal-room/${ctx.bookingId}`, ctx.owner.token);
    expect(room.quote.quote_id).not.toBe(ctx.quoteId);
    expect(room.quote.honorarium_rub).toBe(97000);
    expect(room.quote.terms).toBe('Сет 2 часа, без изменения райдера');
    expect(Date.parse(room.quote.valid_until)).toBeGreaterThan(Date.now());
    expect(room.quote.customer_ack || room.quote.supplier_ack).toBe(false);
    expect(room.can_ack_quote).toBe(true);
  });
}
