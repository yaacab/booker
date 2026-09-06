import { expect, test } from "@playwright/test";
import { DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

test.describe("E16 supply nav: Calendar ≠ Requests", () => {
  test("performer: chrome and section URLs differ", async ({ page, request }) => {
    const session = await login(request, DEMO_ACCOUNTS.artist);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "artist");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/cabinet/performer");

    const chrome = page.getByRole("navigation", { name: "Мобильная навигация" });
    const calendarLink = chrome.getByRole("link", { name: "Календарь" });
    await expect(calendarLink).toBeVisible({ timeout: 15_000 });
    const requestsLink = chrome.getByRole("link", { name: "Заявки" });
    await expect(calendarLink).toHaveAttribute("href", "/cabinet/performer/calendar");
    await expect(requestsLink).toHaveAttribute("href", "/cabinet/performer/requests");
    expect(await calendarLink.getAttribute("href")).not.toBe(await requestsLink.getAttribute("href"));

    await calendarLink.click();
    await expect(page).toHaveURL(/\/cabinet\/performer\/calendar/);
    await expect(page.getByRole("heading", { name: "Расписание", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Входящие", exact: true })).toHaveCount(0);

    await requestsLink.click();
    await expect(page).toHaveURL(/\/cabinet\/performer\/requests/);
    await expect(page.getByRole("heading", { name: "Входящие", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Расписание", exact: true })).toHaveCount(0);
  });

  test("venue: section nav calendar vs requests", async ({ page, request }) => {
    const session = await login(request, DEMO_ACCOUNTS.venue);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "venue");
    expect(org?.id).toBeTruthy();
    await injectSession(page, session.token, org!.id);
    await page.goto("/cabinet/venue/calendar");
    await expect(page.getByRole("navigation", { name: "Разделы кабинета" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Разделы кабинета" }).getByRole("link", { name: "Календарь" }),
    ).toHaveAttribute("aria-current", "page");
    await page
      .getByRole("navigation", { name: "Разделы кабинета" })
      .getByRole("link", { name: "Заявки" })
      .click();
    await expect(page).toHaveURL(/\/cabinet\/venue\/requests/);
    await expect(page.getByRole("heading", { name: "Заявки и сделки" })).toBeVisible();
  });
});
