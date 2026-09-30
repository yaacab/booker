import { expect, test } from "@playwright/test";
import { API_BASE, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Promotion ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-COM-05/06/07 campaign checkout, labelled placement and busy exclusion", async ({ page, request }, testInfo) => {
      const unique = `${width}-${Date.now()}`;
      const city = `Тест продвижения ${unique}`;
      const user = await register(request, `promotion-${unique}@booker.test`, "Артист продвижения");
      const org = await postJson<{ id: string }>(request, "/orgs", user.token, { name: "Студия продвижения", kind: "artist" });
      const start = new Date(Date.now() + 14 * 86400_000);
      start.setUTCHours(18, 0, 0, 0);
      const end = new Date(start.getTime() + 4 * 3600_000);
      const profiles: string[] = [];
      for (let i = 0; i < 5; i += 1) {
        const artist = await postJson<{ id: string }>(request, "/artists", user.token, { organization_id: org.id, name: `Сцена ${i}`, city, category: "dj" });
        profiles.push(artist.id);
        await postJson(request, "/slots", user.token, { resource_type: "artist", resource_id: artist.id, starts_at: start.toISOString(), ends_at: end.toISOString() });
        await postJson(request, `/artists/${artist.id}/tariffs`, user.token, { title: "Сет", honorarium_rub: 20000 });
      }
      await injectSession(page, user.token, org.id);
      await page.goto("/cabinet/performer/growth");
      const promotion = page.getByRole("region", { name: "Продвижение", exact: true });
      await promotion.getByRole("combobox", { name: "Профиль", exact: true }).selectOption(profiles[0]);
      await promotion.getByRole("button", { name: "Создать продвижение", exact: true }).click();
      await expect(promotion).toContainText("Ожидает оплаты");
      await promotion.getByRole("button", { name: "Завершить тестовую оплату продвижения" }).click();
      await expect(promotion).toContainText("Идёт продвижение");
      await expect(page.getByRole("region", { name: "Заказы и оплата" })).toContainText("Тестовый заказ");
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: testInfo.outputPath("promotion-cabinet.png"), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const params = new URLSearchParams({ city, kind: "artist", category: "dj", date: start.toISOString().slice(0, 10) });
      await page.goto(`/search?${params}`);
      const cards = page.locator(".catalog-result");
      await expect(cards).toHaveCount(5);
      const sponsored = cards.filter({ hasText: "Продвижение" });
      await expect(sponsored).toHaveCount(1);
      await sponsored.scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: testInfo.outputPath("promotion-search.png"), fullPage: true });
      await sponsored.getByRole("link").first().click();
      await expect(page).toHaveURL(/promotion_touch_id=/);
      await expect.poll(async () => {
        const result = await request.get(`${API_BASE}/commerce/organizations/${org.id}/promotions`, { headers: { Authorization: `Bearer ${user.token}` } });
        return (await result.json()).items[0].clicks;
      }).toBe(1);
      // Marking the resource busy removes it from all eligible paid candidates.
      await postJson(request, "/calendar/vacation", user.token, { organization_id: org.id, resource_type: "artist", resource_id: profiles[0], starts_at: start.toISOString(), ends_at: end.toISOString() });
      await page.goto(`/search?${params}`);
      await expect(cards).toHaveCount(4);
      await expect(cards.filter({ hasText: "Продвижение" })).toHaveCount(0);
      await expect(cards.filter({ hasText: "Сцена 0" })).toHaveCount(0);
    });
  });
}
