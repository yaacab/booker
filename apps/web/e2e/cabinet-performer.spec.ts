import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

test.describe("Performer cabinet §12 scenarios", () => {
  test.setTimeout(90_000);

  test("sections: vitrina, requests inbox, calendar overview", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.artist);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "artist");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);

    await page.goto("/cabinet/performer");
    await expect(page.getByRole("heading", { name: "Календарь исполнителя" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByRole("heading", { name: "Пока тихо" })
        .or(page.getByRole("heading", { name: "Витрина и услуги" }))
        .first(),
    ).toBeVisible();
    await expect(
      page
        .getByRole("link", { name: "Услуги и витрина" })
        .or(page.getByRole("link", { name: "Настроить витрину" }))
        .first(),
    ).toBeVisible();

    await page.goto("/cabinet/performer/services");
    await expect(page.getByRole("heading", { name: "Витрина и услуги" })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#cabinet-widget-услуги")).toBeVisible();
    await expect(
      page
        .getByTestId("performer-portfolio-summary")
        .or(page.getByText("Создайте профиль"))
        .or(page.locator("#cabinet-widget-витрина-и-райдер"))
        .first(),
    ).toBeVisible();

    const publicLink = page.getByTestId("performer-public-link");
    if (await publicLink.count()) {
      await expect(publicLink).toHaveAttribute("href", /\/artists\//);
    }

    await page.goto("/cabinet/performer/requests");
    await expect(page.locator(".cabinet-zone-title", { hasText: "Входящие" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByTestId("performer-requests-inbox")
        .or(page.locator("#cabinet-widget-новые-заявки"))
        .or(page.locator("#cabinet-widget-все-входящие"))
        .first(),
    ).toBeVisible();
    await expect(page.locator(".cabinet-zone-title", { hasText: "Расписание" })).toHaveCount(0);

    await page.goto("/cabinet/performer/calendar");
    await expect(page.locator(".cabinet-zone-title", { hasText: "Расписание" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByTestId("performer-calendar-overview")
        .or(page.locator("#cabinet-widget-обзор-календаря"))
        .or(page.getByText("Откройте свободные слоты"))
        .first(),
    ).toBeVisible();
    await expect(page.locator(".cabinet-zone-title", { hasText: "Входящие" })).toHaveCount(0);
  });
});
