import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Repeat event ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-REPEAT-01 completed deal becomes clean draft and availability is rechecked", async ({ page, request }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const customer = await register(request, `repeat-c-${suffix}@booker.test`, "Заказчик");
      const supplier = await register(request, `repeat-s-${suffix}@booker.test`, "Артист");
      const org = await postJson<{ id: string }>(request, "/orgs", customer.token, { name: "События", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", supplier.token, { name: "Музыка", kind: "artist" });
      const city = `Город повторов ${suffix}`;
      const artist = await postJson<{ id: string }>(request, "/artists", supplier.token, { organization_id: supply.id, name: "DJ Повтор", category: "dj", city });
      const oldDay = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10);
      const newDay = new Date(Date.now() + 40 * 86400000).toISOString().slice(0, 10);
      const event = await postJson<{ id: string; requirements: { id: string }[] }>(request, "/events", customer.token, { organization_id: org.id, title: "Первый корпоратив", city, event_type: "Корпоратив", event_date: `${oldDay}T15:00:00Z`, ends_at: `${oldDay}T18:00:00Z`, guest_count: 80, budget_rub: 180000, requirements: [{ category_code: "dj" }, { category_code: "photo", required: false }] });
      const slot = await postJson<{ id: string }>(request, "/slots", supplier.token, { resource_type: "artist", resource_id: artist.id, starts_at: `${oldDay}T14:00:00Z`, ends_at: `${oldDay}T19:00:00Z` });
      const req = await postJson<{ id: string }>(request, `/events/${event.id}/requests`, customer.token, { resource_type: "artist", resource_id: artist.id, requirement_id: event.requirements[0].id });
      const offer = await postJson<{ id: string; booking_id: string }>(request, `/requests/${req.id}/offers`, supplier.token, { slot_id: slot.id, honorarium_rub: 90000 });
      for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) await postJson(request, `/offers/${offer.id}/ack`, actor.token, { side });
      await postJson(request, `/bookings/${offer.booking_id}/hold`, customer.token, {});
      const contract = await postJson<{ id: string }>(request, `/bookings/${offer.booking_id}/contract`, customer.token, {});
      for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) {
        const inbox = await getJson<{ items: { entity_id: string; body: string }[] }>(request, "/notifications?limit=100", actor.token);
        const otp = inbox.items.find((n) => n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0]; expect(otp).toBeTruthy();
        await postJson(request, `/contracts/${contract.id}/sign`, actor.token, { side, otp });
      }
      const payment = await postJson<{ id: string }>(request, `/bookings/${offer.booking_id}/payments`, customer.token, { idempotency_key: `repeat-payment-${suffix}` });
      await postJson(request, `/payments/${payment.id}/stub-complete`, customer.token, {});
      await postJson(request, `/events/${event.id}/check-in`, customer.token, {});
      await postJson(request, `/events/${event.id}/check-out`, customer.token, {});
      expect((await getJson<{ status: string }>(request, `/events/${event.id}`, customer.token)).status).toBe("Completed");
      await injectSession(page, customer.token, org.id);
      await page.goto(`/events/${event.id}`);
      const panel = page.getByRole("region", { name: "Повторить событие", exact: true });
      await expect(panel.getByRole("checkbox", { name: "DJ Повтор", exact: true })).toBeVisible();
      await panel.getByLabel("Название нового события", { exact: true }).fill("Второй корпоратив");
      await panel.getByLabel("Новое начало, по Москве", { exact: true }).fill(`${newDay}T18:00`);
      await panel.getByLabel("Новое окончание, по Москве", { exact: true }).fill(`${newDay}T21:00`);
      await panel.getByRole("checkbox", { name: "DJ Повтор", exact: true }).check();
      let lose = true;
      await page.route(`${API_BASE}/events/${event.id}/repeat`, async (route) => { if (lose) { lose = false; expect((await route.fetch()).status()).toBe(201); await route.abort("failed"); } else await route.continue(); });
      await panel.getByRole("button", { name: "Создать новое событие", exact: true }).click();
      await expect(panel.getByRole("alert")).toBeVisible();
      await panel.getByRole("button", { name: "Создать новое событие", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Второй корпоратив", exact: true })).toBeVisible();
      const repeatedId = page.url().split("/").pop(); expect(repeatedId).not.toBe(event.id);
      const repeated = await getJson<{ status: string; requests: object[]; requirements: object[]; budget_rub: number | null }>(request, `/events/${repeatedId}`, customer.token);
      expect(repeated.status).toBe("Draft"); expect(repeated.requests).toHaveLength(0); expect(repeated.requirements).toHaveLength(2); expect(repeated.budget_rub).toBeNull();
      expect((await getJson<{ items: object[] }>(request, `/events?organization_id=${org.id}`, customer.token)).items).toHaveLength(2);
      const preferences = page.getByRole("region", { name: "Предпочтения из прошлого события", exact: true });
      await expect(preferences.getByRole("button", { name: "Включить в состав: DJ Повтор", exact: true })).toBeDisabled();
      await postJson(request, "/slots", supplier.token, { resource_type: "artist", resource_id: artist.id, starts_at: `${newDay}T14:00:00Z`, ends_at: `${newDay}T19:00:00Z` });
      await preferences.getByRole("button", { name: "Перепроверить предпочтения" }).click();
      await expect(preferences.getByRole("button", { name: "Включить в состав: DJ Повтор", exact: true })).toBeEnabled();
      await preferences.getByRole("button", { name: "Включить в состав: DJ Повтор", exact: true }).click();
      await expect(preferences).toContainText("Уже в предварительном составе");
      await expect(page.getByRole("region", { name: "Предварительный состав", exact: true }).getByRole("link", { name: "DJ Повтор", exact: true })).toBeVisible();
      expect((await getJson<{ requests: object[] }>(request, `/events/${repeatedId}`, customer.token)).requests).toHaveLength(0);
      expect((await getJson<{ status: string; requests: object[] }>(request, `/events/${event.id}`, customer.token)).status).toBe("Completed");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await preferences.evaluate((el) => window.scrollBy({ top: el.getBoundingClientRect().top - (document.querySelector("header.top")?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }));
      await page.screenshot({ path: testInfo.outputPath("repeat-preferences.png") });
    });
  });
}
