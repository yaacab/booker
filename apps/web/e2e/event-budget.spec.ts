import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

const SAFE_SERVICE_ERROR = "Сервис временно недоступен. Попробуйте ещё раз позже.";
for (const width of [1440, 390]) {
  test.describe(`Event budget ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-CUST-03 alternatives, selected quote, budget deficit and confirmed transfer", async ({ page, request }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const city = `Город бюджета ${suffix}`;
      const customer = await register(request, `budget-c-${suffix}@booker.test`, "Организатор");
      const supplier = await register(request, `budget-s-${suffix}@booker.test`, "Исполнитель");
      const org = await postJson<{ id: string }>(request, "/orgs", customer.token, { name: "Заказчик", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", supplier.token, { name: "Артисты", kind: "artist" });
      const start = new Date(Date.now() + 30 * 86400000).toISOString();
      const end = new Date(Date.now() + 30 * 86400000 + 3 * 3600000).toISOString();
      const event = await postJson<{ id: string; requirements: { id: string }[] }>(request, "/events", customer.token, { organization_id: org.id, title: "Бюджет корпоратива", city, event_date: start, ends_at: end, guest_count: 50, budget_rub: 200000, requirements: [{ category_code: "dj" }] });
      const offers: { id: string; booking_id: string; artist: string }[] = [];
      for (const [name, price] of [["DJ Первый", 70000], ["DJ Второй", 100000]] as const) {
        const artist = await postJson<{ id: string }>(request, "/artists", supplier.token, { organization_id: supply.id, name, city, category: "dj" });
        await postJson(request, `/artists/${artist.id}/tariffs`, supplier.token, { title: "Пакет", honorarium_rub: price });
        const slot = await postJson<{ id: string }>(request, "/slots", supplier.token, { resource_type: "artist", resource_id: artist.id, starts_at: start, ends_at: end });
        const req = await postJson<{ id: string }>(request, `/events/${event.id}/requests`, customer.token, { resource_type: "artist", resource_id: artist.id, requirement_id: event.requirements[0].id });
        const offer = await postJson<{ id: string; booking_id: string }>(request, `/requests/${req.id}/offers`, supplier.token, { honorarium_rub: price, slot_id: slot.id });
        offers.push({ ...offer, artist: artist.id });
      }
      await injectSession(page, customer.token, org.id);
      let outage = true;
      await page.route(`${API_BASE}/events/${event.id}/budget-summary`, async (route) => {
        if (outage) { await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Сводка временно недоступна" }) }); }
        else await route.continue();
      });
      await page.goto(`/events/${event.id}`);
      const budget = page.getByRole("region", { name: "Бюджет события", exact: true });
      await expect(budget.getByRole("alert")).toHaveText(SAFE_SERVICE_ERROR);
      outage = false;
      await budget.getByRole("button", { name: "Обновить бюджет", exact: true }).click();
      const metric = (title: string) => budget.locator("dl > div").filter({ has: page.locator("dt", { hasText: title }) }).locator("dd");
      await expect(metric("Учтённые предложения")).toHaveText("0 ₽");
      await expect(budget).toContainText("Расчёт пока неполный");
      const current = page.getByRole("region", { name: "Предварительный состав", exact: true });
      await current.getByRole("combobox", { name: "DJ", exact: true }).selectOption(`artist:${offers[1].artist}:`);
      await current.getByRole("button", { name: "Сохранить изменения состава", exact: true }).click();
      await expect(metric("Учтённые предложения")).toHaveText(/106\s000 ₽/);
      await expect(metric("Остаток после учтённых сумм")).toHaveText(/94\s000 ₽/);
      const context = page.getByRole("form", { name: "Параметры подбора" });
      await page.getByText("Окно и бюджет для подбора", { exact: true }).click();
      await context.getByLabel("Заданный бюджет, ₽").fill("80000");
      await context.getByRole("button", { name: "Сохранить параметры", exact: true }).click();
      await expect(budget).toContainText("Учтённые суммы превышают бюджет");
      await expect(metric("Остаток после учтённых сумм")).toHaveText(/-26\s000 ₽/);
      const chosen = offers[1];
      for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) await postJson(request, `/offers/${chosen.id}/ack`, actor.token, { side });
      await postJson(request, `/bookings/${chosen.booking_id}/hold`, customer.token, {});
      const contract = await postJson<{ id: string }>(request, `/bookings/${chosen.booking_id}/contract`, customer.token, {});
      for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) {
        const inbox = await getJson<{ items: { entity_id: string; body: string }[] }>(request, "/notifications?limit=100", actor.token);
        const otp = inbox.items.find((n) => n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0]; expect(otp).toBeTruthy();
        await postJson(request, `/contracts/${contract.id}/sign`, actor.token, { side, otp });
      }
      const pay = await postJson<{ id: string }>(request, `/bookings/${chosen.booking_id}/payments`, customer.token, { idempotency_key: `budget-${suffix}` });
      await postJson(request, `/payments/${pay.id}/stub-complete`, customer.token, {});
      await budget.getByRole("button", { name: "Обновить бюджет", exact: true }).click();
      await expect(metric("Подтверждённые сделки")).toHaveText(/106\s000 ₽/);
      await expect(metric("Учтённые предложения")).toHaveText("0 ₽");
      await expect(metric("Остаток после учтённых сумм")).toHaveText(/-26\s000 ₽/);
      await budget.getByText("Какие сделки и предложения входят в расчёт", { exact: true }).click();
      await expect(budget.getByText("DJ Первый", { exact: true })).toBeVisible();
      await expect(budget.getByText("DJ Второй", { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await budget.evaluate((element) => { const header = document.querySelector("header.top"); window.scrollBy({ top: element.getBoundingClientRect().top - (header?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("budget-viewport.png") });
    });
  });
}
