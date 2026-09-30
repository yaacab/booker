import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

test.describe("Venue cabinet §13 scenarios", () => {
  test.setTimeout(90_000);

  test("sections: home, halls, stats, calendar ≠ requests", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.venue);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "venue");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);

    await page.goto("/cabinet/venue");
    await expect(page.getByRole("heading", { name: "Кабинет площадки" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Навигация рабочего пространства" }),
    ).toBeVisible();

    await page.goto("/cabinet/venue/halls");
    await expect(
      page.getByRole("heading", { name: "Залы площадки", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Новые заявки" })).toHaveCount(0);

    await page.goto("/cabinet/venue/stats");
    await expect(
      page.getByRole("heading", { name: "Статистика площадки", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Бронирования", level: 2 })).toBeVisible();

    await page.goto("/cabinet/venue/calendar");
    await expect(page).toHaveURL(/\/cabinet\/venue\/calendar/);
    await expect(
      page.getByRole("heading", { name: "Календарь площадки", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });

    await page.goto("/cabinet/venue/requests");
    await expect(page).toHaveURL(/\/cabinet\/venue\/requests/);
    await expect(
      page.getByRole("heading", { name: "Заявки площадке", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page).not.toHaveURL(/\/calendar/);
  });
});
