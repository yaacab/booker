import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login, seedRequestAwaitingOffer } from "./helpers";

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
    const performerCabinet = page.locator('main[data-cabinet="performer"]');
    await expect(performerCabinet.getByRole("heading", { level: 1, name: "Кабинет артиста" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(performerCabinet.getByRole("heading", { name: "Новые заявки", exact: true })).toBeVisible();
    await expect(performerCabinet.getByRole("heading", { name: "Открытые слоты", exact: true })).toBeVisible();
    await expect(performerCabinet.getByRole("link", { name: "Подобрать выступления", exact: true })).toHaveAttribute("href", "/briefs");

    await page.goto("/cabinet/performer/services");
    await expect(page.getByRole("heading", { level: 1, name: "Услуги артиста" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Услуги", exact: true })).toBeVisible();
    await expect(page.getByTestId("performer-service-form")).toBeVisible();
    await expect(page.getByTestId("performer-portfolio-summary")).toBeVisible();

    const publicLink = page.getByTestId("performer-public-link");
    await expect(publicLink).toHaveAttribute("href", /\/artists\//);

    await page.goto("/cabinet/performer/requests");
    await expect(page.getByRole("heading", { level: 1, name: "Заявки артисту" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("region", { name: "Входящие заявки" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Фильтр заявок" })).toBeVisible();
    await expect(page.getByTestId("performer-requests-inbox")).toBeVisible();
    await expect(page.getByTestId("performer-calendar-overview")).toHaveCount(0);

    await page.goto("/cabinet/performer/calendar");
    await expect(page.getByRole("heading", { level: 1, name: "Календарь артиста" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("performer-calendar-overview")).toBeVisible();
    await expect(page.getByRole("link", { name: "Импорт календаря и отпуск →", exact: true })).toHaveAttribute("href", "#supply-settings");
    await expect(page.getByTestId("performer-requests-inbox")).toHaveCount(0);
  });
});

for (const width of [1440, 390]) {
  test(`Offer requires an explicit honorarium without a tariff at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const seed = await seedRequestAwaitingOffer(request, { withoutTariff: true });
    await injectSession(page, seed.ownerToken, seed.artistOrgId);
    await page.goto('/cabinet/performer/requests');
    const card = page.getByTestId('performer-requests-inbox').getByRole('article').filter({ hasText: seed.eventTitle });
    await expect(card).toContainText('Тариф не указан');
    const price = card.getByRole('spinbutton', { name: 'Гонорар предложения, ₽' });
    await expect(price).toHaveValue('');
    await card.getByRole('button', { name: 'Отправить предложение' }).click();
    await expect(price).toBeFocused();
    await price.fill('73500');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('explicit-offer-price.png'), fullPage: true });
    const sent = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/offers'));
    await card.getByRole('button', { name: 'Отправить предложение' }).click();
    expect((await sent).postDataJSON().honorarium_rub).toBe(73500);
    await expect(page).toHaveURL(/\/deals\//);
  });
}
