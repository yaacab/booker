import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth, DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

test.describe("Cabinet a11y §7.5", () => {
  test.setTimeout(60_000);

  test("landmarks, skip links и клавиатурный фокус", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    if (!org) throw new Error("Demo customer org missing — run make seed");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/customer");

    await expect(page.getByRole("heading", { level: 1, name: "Студия событий" })).toBeVisible({
      timeout: 15_000,
    });

    const main = page.locator("main.customer-cabinet");
    await expect(main).toHaveAttribute("aria-labelledby", "cabinet-heading");

    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveAttribute("href", "#content");

    const skipToWidgets = page.getByRole("link", { name: "К виджетам кабинета" });
    if (await skipToWidgets.isVisible()) {
      await skipToWidgets.focus();
      await page.keyboard.press("Enter");
      await expect(page.locator("#cabinet-widgets")).toBeInViewport();
    }

    const widgetsRegion = page.getByRole("region", { name: "Виджеты кабинета" });
    if (await widgetsRegion.isVisible()) {
      const firstWidgetLink = widgetsRegion.locator(".dashboard-list a").first();
      if (await firstWidgetLink.count()) {
        await firstWidgetLink.focus();
        await expect(firstWidgetLink).toBeFocused();
      }
    }

    await expect(page.getByRole("button", { name: "Выйти из аккаунта" })).toBeVisible();
  });

  test("performer cabinet: widget sections с aria-labelledby", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.artist);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "artist");
    if (!org) throw new Error("Demo artist org missing — run make seed");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/performer");

    await expect(page.getByRole("heading", { level: 1, name: "Календарь исполнителя" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { level: 2, name: "Свободные слоты" })).toBeVisible();

    const widget = page.locator("section.dashboard-widget").first();
    if (await widget.count()) {
      const labelledBy = await widget.getAttribute("aria-labelledby");
      expect(labelledBy).toBeTruthy();
      if (labelledBy) {
        await expect(page.locator(`#${labelledBy}`)).toBeVisible();
      }
    }
  });
});
