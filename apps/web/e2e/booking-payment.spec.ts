import { expect, test } from "@playwright/test";
import { getJson, injectSession, postJson, seedNegotiation } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Booking payment ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("signed booking uses explicit test capture and honest payment status", async ({ page, request }, testInfo) => {
      const seed = await seedNegotiation(request);
      for (const [side, actor] of [["customer", seed.customer], ["supplier", seed.owner]] as const) {
        await postJson(request, `/offers/${seed.offerId}/ack`, actor.token, { side });
      }
      await postJson(request, `/bookings/${seed.bookingId}/hold`, seed.customer.token, {});
      const contract = await postJson<{ id: string }>(request, `/bookings/${seed.bookingId}/contract`, seed.customer.token, {});
      for (const [side, actor] of [["customer", seed.customer], ["supplier", seed.owner]] as const) {
        const inbox = await getJson<{ items: { entity_id: string; body: string }[] }>(request, "/notifications?limit=100", actor.token);
        const code = inbox.items.find((n) => n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0];
        expect(code).toBeTruthy();
        await postJson(request, `/contracts/${contract.id}/sign`, actor.token, { side, otp: code });
      }
      await injectSession(page, seed.customer.token, seed.customer.orgId);
      await page.goto(`/deals/${seed.bookingId}`);
      await expect(page.getByText("Тестовая оплата: деньги не списываются", { exact: true })).toBeVisible();
      await page.getByRole("tab", { name: "Платежи", exact: true }).click();
      await page.getByRole("button", { name: "Счёт", exact: true }).click();
      await page.getByRole("button", { name: "Тест: подтвердить оплату", exact: true }).click();
      await page.getByRole("tab", { name: "Платежи", exact: true }).click();
      await expect(page.getByRole("tabpanel").getByText(/Тест подтверждён · деньги не списывались/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Тест: подтвердить оплату" })).toHaveCount(0);
      const room = await getJson<{ status: string; payment: { status: string; provider: string } }>(request, `/deal-room/${seed.bookingId}`, seed.customer.token);
      expect(room.status).toBe("Confirmed");
      expect(room.payment).toMatchObject({ status: "succeeded", provider: "stub" });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("booking-test-payment.png"), fullPage: true });
    });
  });
}

test("disabled capabilities leave the deal readable and hide test capture", async ({ page, request }) => {
  const seed = await seedNegotiation(request);
  await injectSession(page, seed.customer.token, seed.customer.orgId);
  // UI unavailable-state fixture; API production-gate rejection is covered independently.
  await page.route(`**/deal-room/${seed.bookingId}`, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.payment_capabilities = { available: false, test_mode: false, can_create: false, can_test_complete: false, message: "Оплата пока недоступна: платёжный партнёр не подключён" };
    await route.fulfill({ response, json: body });
  });
  await page.goto(`/deals/${seed.bookingId}`);
  await expect(page.getByText("Оплата пока недоступна: платёжный партнёр не подключён", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Платежи", exact: true }).click();
  await expect(page.getByRole("button", { name: "Счёт", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Тест: подтвердить оплату" })).toHaveCount(0);
  await expect(page.getByText(`quote_id: ${seed.quoteId}`).first()).toBeVisible();
});

for (const width of [1440, 390]) {
  test.describe(`Checkout receipt ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("uncertain session and private redirect have clear states", async ({ page, request }) => {
      const seed = await seedNegotiation(request);
      await injectSession(page, seed.customer.token, seed.customer.orgId);
      let ready = false;
      // Provider-boundary UI fixture; durable receipt/auth are exercised by API/PG tests.
      await page.route(`**/deal-room/${seed.bookingId}`, async (route) => {
        const response = await route.fetch();
        const body = await response.json();
        body.payment = { id: "receipt-fixture", status: "pending", amount_rub: 106000, provider: "sandbox-fixture", session_state: ready ? "ready" : "uncertain", checkout_url: ready ? "https://pay.example.test/private-session" : null };
        body.payment_capabilities = { available: true, test_mode: false, can_create: true, can_test_complete: false, can_checkout: ready, message: "Счёт подготовлен партнёром" };
        await route.fulfill({ response, json: body });
      });
      await page.goto(`/deals/${seed.bookingId}`);
      await page.getByRole("tab", { name: "Платежи", exact: true }).click();
      await expect(page.getByRole("status").filter({ hasText: "Создание счёта ещё не подтверждено" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Перейти к оплате", exact: true })).toHaveCount(0);
      ready = true;
      await page.reload();
      await page.getByRole("tab", { name: "Платежи", exact: true }).click();
      const redirect = page.getByRole("link", { name: "Перейти к оплате", exact: true });
      await expect(redirect).toHaveAttribute("href", "https://pay.example.test/private-session");
      await expect(redirect).toHaveAttribute("rel", "noreferrer");
      await redirect.focus();
      await expect(redirect).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  });
}
