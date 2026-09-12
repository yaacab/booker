import { expect, test } from "@playwright/test";
import { API_BASE, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Growth ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-GROWTH-01 observed funnel, Free access and Pro periods", async ({ page, request, browser }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const owner = await register(request, `growth-owner-${suffix}@booker.test`, "Артист роста");
      const org = await postJson<{ id: string }>(request, "/orgs", owner.token, { name: "Сцена роста", kind: "artist" });
      const city = `Рост ${suffix}`;
      const artist = await postJson<{ id: string }>(request, "/artists", owner.token, { organization_id: org.id, name: "Новая сцена", category: "dj", city });
      const date = new Date(Date.now() + 15 * 86400_000); date.setUTCHours(18,0,0,0);
      await postJson(request, "/slots", owner.token, { resource_type: "artist", resource_id: artist.id, starts_at: date.toISOString(), ends_at: new Date(date.getTime() + 4 * 3600_000).toISOString() });
      await postJson(request, `/artists/${artist.id}/tariffs`, owner.token, { title: "Сет", honorarium_rub: 30000 });
      const guestContext = await browser.newContext({ viewport: { width, height: 900 } });
      const guest = await guestContext.newPage();
      const base = testInfo.project.use.baseURL!;
      await guest.goto(`${base}/search?${new URLSearchParams({ city, kind: "artist", date: date.toISOString().slice(0,10) })}`);
      const card = guest.locator(".catalog-result").filter({ hasText: "Новая сцена" });
      await expect(card).toBeVisible();
      await card.scrollIntoViewIfNeeded();
      await card.getByRole("link").first().click();
      await expect(guest.getByRole("heading", { name: "Новая сцена", exact: true })).toBeVisible();
      const customer = await register(request, `growth-customer-${suffix}@booker.test`, "Заказчик");
      const customerOrg = await postJson<{ id: string }>(request, "/orgs", customer.token, { name: "Заказчик роста", kind: "customer" });
      await postJson(request, "/favorites", customer.token, { organization_id: customerOrg.id, target_type: "artist", target_id: artist.id });
      const event = await postJson<{ id: string }>(request, "/events", customer.token, { organization_id: customerOrg.id, title: "Событие", city, event_date: date.toISOString() });
      await postJson(request, `/events/${event.id}/requests`, customer.token, { resource_type: "artist", resource_id: artist.id });
      await expect.poll(async () => {
        const r = await request.get(`${API_BASE}/organizations/${org.id}/growth`, { headers: { Authorization: `Bearer ${owner.token}` } });
        return (await r.json()).funnel.profile_views;
      }).toBe(1);
      await guestContext.close();
      await injectSession(page, owner.token, org.id);
      await page.goto("/cabinet/performer/growth");
      const growth = page.getByRole("region", { name: "Результаты и рост" });
      await expect(growth.getByRole("heading", { name: "Ваши результаты" })).toBeVisible();
      for (const label of ["Показы в каталоге", "Просмотры профиля", "Добавления в избранное", "Заявки"]) {
        await expect(growth.locator(".growth-metrics > div").filter({ hasText: label }).locator("dd")).toHaveText("1");
      }
      await expect(growth.getByRole("button", { name: "90 дней", exact: true })).toBeDisabled();
      await expect(growth).toContainText("пока нет ответов");
      await expect(growth).toContainText("0 ₽");
      const order = await postJson<{ id: string }>(request, `/commerce/organizations/${org.id}/orders`, owner.token, { plan_code: "artist_pro", billing_period: "monthly", idempotency_key: `growth-${suffix}` });
      await postJson(request, `/commerce/orders/${order.id}/test-complete`, owner.token, { status: "paid" });
      await page.reload();
      const ninety = growth.getByRole("button", { name: "90 дней", exact: true });
      await expect(ninety).toBeEnabled(); await ninety.click();
      await expect(ninety).toHaveAttribute("aria-pressed", "true");
      await expect(growth).toContainText("Закрытых заявок за период нет.");
      await expect(growth.getByRole("button", { name: "365 дней", exact: true })).toBeDisabled();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: testInfo.outputPath("growth.png"), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  });
}

test("Growth recovers after an API failure", async ({ page, request }) => {
  const suffix = Date.now();
  const owner = await register(request, `growth-error-${suffix}@booker.test`, "Рост");
  const org = await postJson<{ id: string }>(request, "/orgs", owner.token, { name: "Рост", kind: "artist" });
  await injectSession(page, owner.token, org.id);
  await page.route("**/organizations/*/growth?*", (route) => route.abort());
  await page.goto("/cabinet/performer/growth");
  const growth = page.getByRole("region", { name: "Результаты и рост" });
  await expect(growth.getByRole("alert")).toBeVisible();
  await page.unroute("**/organizations/*/growth?*");
  await growth.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(growth).toContainText("Создайте профиль и откройте свободные даты");
});
