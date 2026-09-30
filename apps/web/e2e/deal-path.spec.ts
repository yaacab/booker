import { expect, test } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  getJson,
  injectSession,
  postJson,
  seedNegotiation,
  register,
  seedRequestAwaitingOffer,
  seedSameSlotHoldRace,
} from "./helpers";

type DealRoomQuote = {
  quote_id: string;
  honorarium_rub: number;
  total_rub: number;
  customer_ack?: boolean;
  supplier_ack?: boolean;
  terms?: string;
  active?: boolean;
};

test.describe("Deal path E07–E09", () => {
  test.setTimeout(120_000);

  test("E07: заявка → оффер — одна сущность, одинаковые условия с обеих сторон", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    // UI-path (awaiting-offer) + API negotiation: одна сущность quote с обеих сторон.
    const seed = await seedRequestAwaitingOffer(request);
    const negotiation = await seedNegotiation(request, {
      honorariumRub: 88_000,
      terms: "E07: общий quote",
      slotStartsAt: "2026-12-01T18:00:00+00:00",
      slotEndsAt: "2026-12-01T22:00:00+00:00",
    });

    await test.step("supplier: Deal Room показывает актуальный гонорар", async () => {
      await injectSession(page, negotiation.owner.token, negotiation.owner.orgId);
      await page.goto(`/deals/${negotiation.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await expect(
        page.getByText(negotiation.honorariumRub.toLocaleString("ru-RU"), { exact: false }).first(),
      ).toBeVisible();
    });

    await test.step("API: customer и supplier видят один и тот же quote", async () => {
      const supplierRoom = await getJson<{ offer_id: string; quote: DealRoomQuote }>(
        request,
        `/deal-room/${negotiation.bookingId}`,
        negotiation.owner.token,
        negotiation.owner.orgId,
      );
      const customerRoom = await getJson<{ offer_id: string; quote: DealRoomQuote }>(
        request,
        `/deal-room/${negotiation.bookingId}`,
        negotiation.customer.token,
        negotiation.customer.orgId,
      );

      expect(supplierRoom.offer_id).toBe(negotiation.offerId);
      expect(customerRoom.offer_id).toBe(negotiation.offerId);
      expect(supplierRoom.quote.quote_id).toBe(negotiation.quoteId);
      expect(customerRoom.quote.quote_id).toBe(negotiation.quoteId);
      expect(supplierRoom.quote.honorarium_rub).toBe(negotiation.honorariumRub);
      expect(customerRoom.quote.honorarium_rub).toBe(negotiation.honorariumRub);
      expect(customerRoom.quote.total_rub).toBe(supplierRoom.quote.total_rub);
    });

    await test.step("customer UI: те же условия в Deal Room", async () => {
      await injectSession(page, negotiation.customer.token, negotiation.customer.orgId);
      await page.goto(`/deals/${negotiation.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole("heading", { name: "Итог" })).toBeVisible();
      await expect(
        page.getByText(negotiation.honorariumRub.toLocaleString("ru-RU"), { exact: false }).first(),
      ).toBeVisible();
    });

    // UI-path из awaiting-offer (как flow.spec) — общий booking после кнопки
    await test.step("UI path: артист отправляет предложение из кабинета", async () => {
      await injectSession(page, seed.ownerToken, seed.artistOrgId);
      await page.goto("/cabinet");
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(seed.eventTitle)).toBeVisible();
      await page.getByRole("button", { name: "Отправить предложение" }).click();
      await expect(page).toHaveURL(/\/deals\//, { timeout: 15_000 });
      const bookingId = page.url().split("/deals/")[1]?.split(/[?#]/)[0] ?? "";
      expect(bookingId).toBeTruthy();
      await expect(page.getByTestId("deal-room-accents")).toBeVisible();
      await expect(page.getByText("ожидает подтверждений").first()).toBeVisible();
    });
  });

  test("E08: новая версия сбрасывает ack — hold 409 до re-ack обеих сторон", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const ctx = await seedNegotiation(request, {
      honorariumRub: 100_000,
      terms: "E08 v1",
      slotStartsAt: "2026-12-08T18:00:00+00:00",
      slotEndsAt: "2026-12-08T22:00:00+00:00",
    });

    await test.step("v1: двусторонний ack", async () => {
      await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.owner.token, { side: "supplier" }, ctx.owner.orgId);
      await postJson(
        request,
        `/offers/${ctx.offerId}/ack`,
        ctx.customer.token,
        { side: "customer" },
        ctx.customer.orgId,
      );
      const room = await getJson<{ quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.quote.supplier_ack).toBe(true);
      expect(room.quote.customer_ack).toBe(true);
      expect(room.quote.quote_id).toBe(ctx.quoteId);
    });

    const v2 = await test.step("v2: новая смета, старые ack не действуют", async () => {
      const bumped = await postJson<{
        id: string;
        quote_id: string;
        honorarium_rub: number;
        active: boolean;
      }>(
        request,
        `/offers/${ctx.offerId}/versions`,
        ctx.owner.token,
        { honorarium_rub: 120_000, terms: "E08 v2: новая смета" },
        ctx.owner.orgId,
      );
      expect(bumped.active).toBe(false);
      expect(bumped.quote_id).toBe(bumped.id);
      expect(bumped.quote_id).not.toBe(ctx.quoteId);
      expect(bumped.honorarium_rub).toBe(120_000);

      const room = await getJson<{ quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.quote.quote_id).toBe(bumped.quote_id);
      expect(room.quote.customer_ack).toBe(false);
      expect(room.quote.supplier_ack).toBe(false);
      return bumped;
    });

    await test.step("hold 409 без re-ack", async () => {
      const hold = await request.post(`${API_BASE}/bookings/${ctx.bookingId}/hold`, {
        headers: {
          Authorization: `Bearer ${ctx.customer.token}`,
          "Content-Type": "application/json",
          "X-Booker-Org": ctx.customer.orgId,
        },
      });
      expect(hold.status()).toBe(409);
    });

    await test.step("только supplier re-ack — hold всё ещё 409", async () => {
      await injectSession(page, ctx.owner.token, ctx.owner.orgId);
      await page.goto(`/deals/${ctx.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтвердил только исполнитель").first()).toBeVisible({ timeout: 10_000 });

      const hold = await request.post(`${API_BASE}/bookings/${ctx.bookingId}/hold`, {
        headers: {
          Authorization: `Bearer ${ctx.customer.token}`,
          "Content-Type": "application/json",
          "X-Booker-Org": ctx.customer.orgId,
        },
      });
      expect(hold.status()).toBe(409);
    });

    await test.step("customer re-ack → hold 200; UI показывает удержание", async () => {
      await injectSession(page, ctx.customer.token, ctx.customer.orgId);
      await page.goto(`/deals/${ctx.bookingId}`);
      await expect(page.getByText(v2.honorarium_rub.toLocaleString("ru-RU"), { exact: false }).first()).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтверждено обеими сторонами").first()).toBeVisible({ timeout: 10_000 });

      const held = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith(`/bookings/${ctx.bookingId}/hold`));
      await page.locator(".deal-aside").getByRole("button", { name: "Удержать дату", exact: true }).click();
      expect((await held).status()).toBe(200);
      await expect(page.getByText("Дата удерживается").first()).toBeVisible({ timeout: 10_000 });

      const room = await getJson<{ hold?: { status: string }; quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.hold?.status).toBe("active");
      expect(room.quote.quote_id).toBe(v2.quote_id);
      expect(room.quote.honorarium_rub).toBe(120_000);
    });
  });

  test("E09: два hold на один слот — ровно один 200 и один 409", async ({ request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const race = await seedSameSlotHoldRace(request);

    const first = await request.post(`${API_BASE}/bookings/${race.bookingId}/hold`, {
      headers: {
        Authorization: `Bearer ${race.customer.token}`,
        "Content-Type": "application/json",
        "X-Booker-Org": race.customer.orgId,
      },
    });
    const second = await request.post(`${API_BASE}/bookings/${race.bookingId2}/hold`, {
      headers: {
        Authorization: `Bearer ${race.customer2.token}`,
        "Content-Type": "application/json",
        "X-Booker-Org": race.customer.orgId,
      },
    });

    expect(sortedStatuses([first.status(), second.status()])).toEqual([200, 409]);

    // stub payments only — не проверяем PSP; exclusivity слота достаточна
    const winnerId = first.status() === 200 ? race.bookingId : race.bookingId2;
    const winnerToken = first.status() === 200 ? race.customer.token : race.customer2.token;
    const room = await getJson<{ status: string; hold?: { status: string } }>(
      request,
      `/deal-room/${winnerId}`,
      winnerToken,
      race.customer.orgId,
    );
    expect(room.hold?.status).toBe("active");
  });
});

function sortedStatuses(codes: number[]): number[] {
  return [...codes].sort((a, b) => a - b);
}

for (const width of [1440, 390]) {
  test(`Viewer cannot hold an acknowledged deal at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const ctx = await seedNegotiation(request);
    await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.owner.token, { side: 'supplier' });
    await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.customer.token, { side: 'customer' });
    const suffix = `${width}-${Date.now()}`;
    const email = `hold-viewer-${suffix}@booker.test`;
    const viewer = await register(request, email, 'Наблюдатель');
    const order = await postJson<{ id: string }>(request, `/commerce/organizations/${ctx.owner.orgId}/orders`, ctx.owner.token, { plan_code: 'artist_pro', billing_period: 'monthly', idempotency_key: suffix });
    await postJson(request, `/commerce/orders/${order.id}/test-complete`, ctx.owner.token, { status: 'paid' });
    const secret = (await import('node:crypto')).randomBytes(32).toString('hex');
    await postJson(request, `/orgs/${ctx.owner.orgId}/team/invitations`, ctx.owner.token, { email, role: 'viewer', secret });
    const accepted = await request.post(`${API_BASE}/team-invitations/accept`, { headers: { Authorization: `Bearer ${viewer.token}`, 'X-Team-Invitation': secret } });
    expect(accepted.ok()).toBe(true);
    await injectSession(page, viewer.token, ctx.owner.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    await expect(page.getByRole('button', { name: 'Удержать дату', exact: true }).first()).toBeDisabled();
    const denied = await request.post(`${API_BASE}/bookings/${ctx.bookingId}/hold`, { headers: { Authorization: `Bearer ${viewer.token}` } });
    expect(denied.status()).toBe(403);
    const before = await getJson<{ status: string; can_hold: boolean }>(request, `/deal-room/${ctx.bookingId}`, ctx.owner.token);
    expect(before.status).toBe('Negotiation');
    expect(before.can_hold).toBe(true);
    await injectSession(page, ctx.owner.token, ctx.owner.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    const holdButton = page.getByRole('button', { name: 'Удержать дату', exact: true }).first();
    await expect(holdButton).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath('hold-action.png') });
    await holdButton.click();
    await expect.poll(async () => (await getJson<{ status: string }>(request, `/deal-room/${ctx.bookingId}`, ctx.owner.token)).status).toBe('DateHeld');
    await page.reload();
    await expect(page.getByText('Дата удерживается', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Удержать дату', exact: true })).toHaveCount(0);
  });
}

for (const width of [1440, 390]) {
  test(`Stale displayed quote cannot acknowledge new terms at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const ctx = await seedNegotiation(request);
    await injectSession(page, ctx.customer.token, ctx.customer.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    const primaryAction = () => width === 390
      ? page.locator('.sticky-cta').getByRole('button', { name: 'Подтвердить условия', exact: true })
      : page.locator('.deal-aside').getByRole('button', { name: 'Подтвердить условия', exact: true });
    await expect(primaryAction()).toBeVisible();
    const updated = await postJson<{ quote_id: string }>(request, `/offers/${ctx.offerId}/versions`, ctx.owner.token, { honorarium_rub: 137000, expected_quote_id: ctx.quoteId });
    const denied = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/offers/${ctx.offerId}/ack`));
    await primaryAction().click();
    expect((await denied).status()).toBe(409);
    await expect(page.getByRole('alert').filter({ hasText: 'Предложение изменилось' })).toBeVisible();
    await page.getByRole('alert').filter({ hasText: 'Предложение изменилось' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('stale-quote.png') });
    const before = await getJson<{ quote: { customer_ack: boolean } }>(request, `/deal-room/${ctx.bookingId}`, ctx.customer.token);
    expect(before.quote.customer_ack).toBe(false);
    await page.getByRole('button', { name: 'Обновить условия', exact: true }).click();
    let refreshedAction = primaryAction();
    if (width === 390) {
      await page.locator('.sticky-cta').getByRole('button', { name: 'Предложение', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Предложение' });
      await expect(dialog.getByText(/137[\s\u00a0]000/, { exact: false }).first()).toBeVisible();
      refreshedAction = dialog.getByRole('button', { name: 'Подтвердить условия', exact: true });
    } else {
      await expect(page.locator('.deal-aside').getByText(/137[\s\u00a0]000/, { exact: false }).first()).toBeVisible();
    }
    const accepted = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/offers/${ctx.offerId}/ack`));
    await refreshedAction.click();
    expect((await accepted).status()).toBe(200);
    const after = await getJson<{ quote: { quote_id: string; customer_ack: boolean; honorarium_rub: number } }>(request, `/deal-room/${ctx.bookingId}`, ctx.customer.token);
    expect(after.quote.quote_id).toBe(updated.quote_id);
    expect(after.quote.customer_ack).toBe(true);
    expect(after.quote.honorarium_rub).toBe(137000);
  });
}

for (const width of [1440, 390]) {
  test(`Contract permissions and signing at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const ctx = await seedNegotiation(request);
    await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.owner.token, { side: 'supplier', quote_id: ctx.quoteId });
    await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.customer.token, { side: 'customer', quote_id: ctx.quoteId });
    await postJson(request, `/bookings/${ctx.bookingId}/hold`, ctx.customer.token, {});
    const email = `contract-viewer-${width}-${Date.now()}@booker.test`;
    const viewer = await register(request, email, 'Наблюдатель');
    const order = await postJson<{ id: string }>(request, `/commerce/organizations/${ctx.owner.orgId}/orders`, ctx.owner.token, { plan_code: 'artist_pro', billing_period: 'monthly', idempotency_key: email.replace("@", ":") });
    await postJson(request, `/commerce/orders/${order.id}/test-complete`, ctx.owner.token, { status: 'paid' });
    const secret = (await import('node:crypto')).randomBytes(32).toString('hex');
    await postJson(request, `/orgs/${ctx.owner.orgId}/team/invitations`, ctx.owner.token, { email, role: 'viewer', secret });
    const accepted = await request.post(`${API_BASE}/team-invitations/accept`, { headers: { Authorization: `Bearer ${viewer.token}`, 'X-Team-Invitation': secret } });
    expect(accepted.ok()).toBe(true);
    const contract = await postJson<{ id: string }>(request, `/bookings/${ctx.bookingId}/contract`, ctx.customer.token, {});
    type Inbox = { items: { template: string; entity_id: string; body: string }[] };
    const inbox = await getJson<Inbox>(request, '/notifications', ctx.owner.token);
    const code = inbox.items.find(n => n.template === 'contract.otp' && n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0];
    expect(code).toBeTruthy();
    const viewerInbox = await getJson<Inbox>(request, '/notifications', viewer.token);
    expect(viewerInbox.items.some(n => n.template === 'contract.otp')).toBe(false);
    await injectSession(page, viewer.token, ctx.owner.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    const signingAction = () => width === 390
      ? page.locator('.sticky-cta').getByRole('button', { name: 'Подписать договор', exact: true })
      : page.locator('.deal-aside').getByRole('button', { name: 'Подписать договор', exact: true });
    await expect(signingAction()).toBeDisabled();
    const denied = await request.post(`${API_BASE}/contracts/${contract.id}/sign`, { headers: { Authorization: `Bearer ${viewer.token}` }, data: { side: 'supplier', otp: code } });
    expect(denied.status()).toBe(403);
    await injectSession(page, ctx.owner.token, ctx.owner.orgId);
    await page.goto(`/deals/${ctx.bookingId}`);
    const field = page.locator('input[autocomplete="one-time-code"]:visible');
    await expect(field).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('contract-signing.png') });
    await field.fill(code!);
    await signingAction().click();
    await expect.poll(async () => (await getJson<{ contract: { supplier_signed: boolean } }>(request, `/deal-room/${ctx.bookingId}`, ctx.owner.token)).contract.supplier_signed).toBe(true);
    await expect(signingAction()).toBeDisabled();
  });
}
