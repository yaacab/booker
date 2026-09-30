import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

test.describe("Customer cabinet §11.2 scenarios", () => {
  test.setTimeout(90_000);

  test("dashboard, favorites, saved-searches, deal progress nav", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);

    await page.goto("/cabinet/customer");
    const cabinet = page.locator('main[data-cabinet="customer"]');
    await expect(cabinet).toBeVisible({ timeout: 15_000 });
    await expect(cabinet.getByRole("heading", { level: 1, name: "Привет, Анна!" })).toBeVisible({ timeout: 15_000 });
    await expect(cabinet.getByRole("region", { name: "Продолжить организацию событий", exact: true })).toBeVisible();
    await expect(cabinet.getByRole("link", { name: "Найти артиста", exact: true }).first()).toHaveAttribute("href", "/search?kind=artist");
    await expect(cabinet.getByRole("link", { name: "Заказы и отклики", exact: true })).toHaveAttribute("href", "/briefs");
    await expect(
      page
        .getByRole("navigation", { name: "Навигация рабочего пространства" })
        .getByRole("link", { name: "Избранное", exact: true }),
    ).toHaveAttribute("href", "/cabinet/customer/favorites");

    await page.goto("/cabinet/customer/favorites");
    await expect(page.getByRole("heading", { name: "Избранное" })).toBeVisible({ timeout: 15_000 });

    await page.goto("/cabinet/customer/saved-searches");
    await expect(page.getByRole("heading", { name: "Сохранённые поиски" })).toBeVisible({
      timeout: 15_000,
    });

    await page.goto("/cabinet/customer/messages");
    await expect(page).toHaveURL(/\/cabinet\/customer\/messages/);
    await expect(page.getByRole("heading", { name: "Сообщения" })).toBeVisible({ timeout: 15_000 });
  });
});
