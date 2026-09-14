import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Team ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("paid seats, invitation retry, join and removal", async ({ page, browser, request }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const owner = await register(request, `team-owner-${suffix}@booker.test`, "Владелец команды");
      const email = `team-guest-${suffix}@booker.test`;
      const guest = await register(request, email, "Коллега Анна");
      const org = await postJson<{ id: string }>(request, "/orgs", owner.token, { name: "Агентство мероприятий", kind: "customer" });
      await injectSession(page, owner.token, org.id);
      await page.goto(`/team?organization=${org.id}`);
      const panel = page.getByRole("region", { name: "Команда организации", exact: true });
      await expect(panel.getByRole("button", { name: "Создать приглашение", exact: true })).toBeDisabled();
      const order = await postJson<{ id: string }>(request, `/commerce/organizations/${org.id}/orders`, owner.token, { plan_code: "customer_business", billing_period: "monthly", idempotency_key: `team-${suffix}` });
      await postJson(request, `/commerce/orders/${order.id}/test-complete`, owner.token, { status: "paid" });
      await panel.getByRole("button", { name: "Обновить команду", exact: true }).click();
      await panel.getByLabel("Email участника", { exact: true }).fill(email);
      await panel.getByRole("combobox", { name: "Роль приглашённого", exact: true }).selectOption("viewer");
      let lose = true;
      await page.route(`${API_BASE}/orgs/${org.id}/team/invitations`, async route => { if (lose) { lose = false; expect((await route.fetch()).status()).toBe(201); await route.abort("failed"); } else await route.continue(); });
      await panel.getByRole("button", { name: "Создать приглашение", exact: true }).click();
      await expect(panel.getByRole("alert")).toBeVisible();
      await panel.getByRole("button", { name: "Создать приглашение", exact: true }).click();
      const input = panel.getByLabel("Ссылка приглашения", { exact: true });
      await expect(input).toBeVisible();
      const link = await input.inputValue();
      const guestContext = await browser.newContext({ viewport: { width, height: 900 } });
      const guestPage = await guestContext.newPage();
      try {
        await injectSession(guestPage, guest.token, org.id);
        await guestPage.goto(link);
        await expect(guestPage.getByRole("heading", { name: "Агентство мероприятий", exact: true })).toBeVisible();
        expect(guestPage.url()).not.toContain("#");
        expect(await guestPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await guestPage.screenshot({ path: testInfo.outputPath("join-team.png") });
        await guestPage.getByRole("button", { name: "Присоединиться к команде", exact: true }).click();
        await expect(guestPage.getByRole("status")).toContainText("Вы присоединились");
        await guestPage.goto(`${new URL(link).origin}/team?organization=${org.id}`);
        await expect(guestPage.getByRole("heading", { name: "Коллега Анна · вы", exact: true })).toBeVisible();
        await expect(guestPage.getByRole("button", { name: "Создать приглашение", exact: true })).toHaveCount(0);
        await panel.getByRole("button", { name: "Обновить команду", exact: true }).click();
        await expect(panel).toContainText("Участников: 2");
        await panel.getByRole("button", { name: "Изменить права: Коллега Анна", exact: true }).click();
        await panel.getByRole("combobox", { name: "Новая роль", exact: true }).selectOption("manager");
        await panel.getByRole("button", { name: "Сохранить права", exact: true }).click();
        await expect(panel.getByRole("article").filter({ hasText: "Коллега Анна" })).toContainText("Менеджер");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await panel.evaluate(el => window.scrollBy({ top: el.getBoundingClientRect().top - (document.querySelector("header.top")?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }));
        await page.screenshot({ path: testInfo.outputPath("team.png"), mask: [input] });
        await panel.getByRole("button", { name: "Удалить из команды: Коллега Анна", exact: true }).click();
        await expect(panel).toContainText("Участников: 1");
        const denied = await request.get(`${API_BASE}/orgs/${org.id}/team`, { headers: { Authorization: `Bearer ${guest.token}` } });
        expect(denied.status()).toBe(403);
        expect((await getJson<{ used: number; reserved: number }>(request, `/orgs/${org.id}/team`, owner.token)).reserved).toBe(0);
      } finally { await guestContext.close(); }
    });
  });
}
