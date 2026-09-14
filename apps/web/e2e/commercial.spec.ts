import { expect, test } from "@playwright/test";
import { API_BASE, injectSession, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Commercial ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("E-COM-01 pricing audiences, annual savings, keyboard and layout", async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/pricing");
      await expect(page.getByRole("heading", { name: /Больше возможностей/ })).toBeVisible();
      const pro = page.getByRole("article", { name: "Тариф Pro", exact: true });
      await expect(pro).toContainText("1 990 ₽");
      await page.screenshot({ path: testInfo.outputPath("pricing.png"), fullPage: true });
      await page.getByRole("button", { name: "За год", exact: true }).click();
      await expect(pro).toContainText("19 900 ₽");
      await expect(pro).toContainText("Экономия 3 980 ₽");
      await page.getByRole("button", { name: "Площадка", exact: true }).click();
      await expect(pro).toContainText("39 900 ₽");
      await page.getByRole("button", { name: "Организатор", exact: true }).click();
      await expect(page.getByRole("article", { name: "Тариф Business", exact: true })).toContainText("49 900 ₽");
      const question = page.getByText("Можно ли купить верификацию или рейтинг?", { exact: true });
      await question.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText(/Верификация, отзывы, число завершённых сделок/)).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });

    test("E-COM-02 Free artist sees current plan and an empty billing history", async ({ page, request }) => {
      const unique = `free-${width}-${Date.now()}`;
      const user = await register(request, `${unique}@booker.test`, "Артист Free");
      const org = await request.post(`${API_BASE}/orgs`, { headers: { Authorization: `Bearer ${user.token}` }, data: { name: "Моя сцена", kind: "artist" } });
      expect(org.ok()).toBe(true);
      const orgId = (await org.json()).id;
      await injectSession(page, user.token, orgId);
      await page.goto("/cabinet/performer/growth");
      const current = page.getByRole("region", { name: "Текущий тариф" });
      await expect(current.getByRole("heading", { name: "Free", exact: true })).toBeVisible();
      await expect(current).toContainText("4 %");
      await expect(page.getByText("Платных заказов пока нет.", { exact: false })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("E-COM-03/E-COM-04 explicit stub upgrade changes persisted entitlements", async ({ page, request }) => {
      const unique = `upgrade-${width}-${Date.now()}`;
      const user = await register(request, `${unique}@booker.test`, "Артист Pro");
      const headers = { Authorization: `Bearer ${user.token}` };
      const org = await request.post(`${API_BASE}/orgs`, { headers, data: { name: "Студия роста", kind: "artist" } });
      expect(org.ok()).toBe(true);
      const orgId = (await org.json()).id;
      await injectSession(page, user.token, orgId);
      await page.goto("/pricing");
      const pro = page.getByRole("article", { name: "Тариф Pro", exact: true });
      await pro.getByRole("button", { name: "Выбрать тариф", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Ожидает оплаты" })).toBeVisible();
      await expect(page.getByText("Тестовый режим: реальные деньги не списываются")).toBeVisible();
      const before = await request.get(`${API_BASE}/commerce/organizations/${orgId}`, { headers });
      expect((await before.json()).plan.code).toBe("artist_free");
      await page.getByRole("button", { name: "Завершить тестовую оплату" }).click();
      await expect(page.getByRole("heading", { name: "Тестовая подписка активирована" })).toBeVisible();
      const after = await request.get(`${API_BASE}/commerce/organizations/${orgId}`, { headers });
      const saved = await after.json();
      expect(saved.plan.code).toBe("artist_pro");
      expect(saved.features["analytics.advanced"]).toBe(true);
      expect(saved.features["promotion.monthly_credits"]).toBe(2);
      await page.getByRole("link", { name: "Перейти к своему тарифу" }).click();
      await expect(page.getByRole("region", { name: "Текущий тариф" })).toContainText("Pro");
      await page.reload();
      await expect(page.getByRole("region", { name: "Текущий тариф" })).toContainText("3 %");
    });
  });
}

test("Pricing recovers from an API error", async ({ page }) => {
  await page.route("**/commerce/catalog", (route) => route.abort());
  await page.goto("/pricing");
  await expect(page.getByRole("alert").filter({ hasText: "Не удалось" })).toBeVisible();
  await page.unroute("**/commerce/catalog");
  await page.getByRole("button", { name: "Повторить загрузку" }).click();
  await expect(page.getByRole("article", { name: "Тариф Pro", exact: true })).toBeVisible();
});

test("Commerce notification selects the specified organization without a silent fallback", async ({ page, request }) => {
  const user = await register(request, `commerce-org-link-${Date.now()}@booker.test`, "Организатор");
  const headers = { Authorization: `Bearer ${user.token}` };
  const firstResponse = await request.post(`${API_BASE}/orgs`, { headers, data: { name: "Первое агентство", kind: "customer" } });
  const secondResponse = await request.post(`${API_BASE}/orgs`, { headers, data: { name: "Второе агентство", kind: "customer", confirm_another_workspace: true } });
  expect(firstResponse.ok() && secondResponse.ok()).toBe(true);
  const first = await firstResponse.json(); const second = await secondResponse.json();
  await injectSession(page, user.token, first.id);
  await page.goto(`/cabinet/customer/business?organization=${second.id}`);
  await expect(page.getByText("Второе агентство", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Текущий тариф", exact: true })).toBeVisible();
  await page.goto('/cabinet/customer/business?organization=00000000-0000-0000-0000-000000000000');
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Нет доступа к указанному рабочему пространству");
  await expect(page.getByRole("region", { name: "Текущий тариф", exact: true })).toHaveCount(0);
});
