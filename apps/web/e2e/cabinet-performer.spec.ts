import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

test.describe("Performer cabinet §12 scenarios", () => {
  test("sections: vitrina, requests inbox, calendar overview", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.artist);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "artist");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);

    await page.goto("/cabinet/performer");
    await expect(page.getByRole("heading", { name: "Витрина и райдер" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Услуги" })).toBeVisible();
    await expect(page.getByTestId("performer-services-list").or(page.getByText("Добавьте услугу"))).toBeVisible();

    await page.goto("/cabinet/performer/services");
    await expect(page.getByRole("heading", { name: "Витрина и услуги" })).toBeVisible();
    await expect(page.getByTestId("performer-portfolio-summary").or(page.getByText("Создайте профиль"))).toBeVisible();

    const publicLink = page.getByTestId("performer-public-link");
    if (await publicLink.count()) {
      await expect(publicLink).toHaveAttribute("href", /\/artists\//);
    }

    await page.goto("/cabinet/performer/requests");
    await expect(page.getByRole("heading", { name: "Входящие" })).toBeVisible();
    await expect(page.getByTestId("performer-requests-inbox").or(page.getByText("Заявки появятся"))).toBeVisible();
    await expect(page.getByRole("heading", { name: "Расписание" })).toHaveCount(0);

    await page.goto("/cabinet/performer/calendar");
    await expect(page.getByRole("heading", { name: "Расписание" })).toBeVisible();
    await expect(page.getByTestId("performer-calendar-overview").or(page.getByText("Откройте свободные слоты"))).toBeVisible();
    await expect(page.getByRole("heading", { name: "Входящие" })).toHaveCount(0);
  });
});
