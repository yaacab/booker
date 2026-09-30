import { expect, test } from "@playwright/test";
import { DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

const ROLES = [
  {
    mode: "performer",
    account: DEMO_ACCOUNTS.artist,
    organizationKind: "artist",
    calendarHeading: "Календарь артиста",
    requestsHeading: "Заявки артисту",
  },
  {
    mode: "venue",
    account: DEMO_ACCOUNTS.venue,
    organizationKind: "venue",
    calendarHeading: "Календарь площадки",
    requestsHeading: "Заявки площадке",
  },
] as const;

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900, navigation: "Навигация рабочего пространства" },
  { name: "390px", width: 390, height: 844, navigation: "Мобильная навигация" },
] as const;

test.describe("E16 supply nav: Calendar ≠ Requests", () => {
  for (const viewport of VIEWPORTS) {
    for (const role of ROLES) {
      test(`${role.mode} on ${viewport.name}: calendar and requests stay distinct`, async ({ page, request }) => {
        const session = await login(request, role.account);
        const me = await fetchMe(request, session.token);
        const org = me.organizations.find((o) => o.kind === role.organizationKind);
        expect(org?.id).toBeTruthy();
        await injectSession(page, session.token, org!.id);
        await page.setViewportSize(viewport);
        await page.goto(`/cabinet/${role.mode}`);

        const navigation = page.getByRole("navigation", { name: viewport.navigation });
        const calendarLink = navigation.getByRole("link", { name: "Календарь", exact: true });
        const requestsLink = navigation.getByRole("link", { name: "Заявки", exact: true });
        const calendarHref = `/cabinet/${role.mode}/calendar`;
        const requestsHref = `/cabinet/${role.mode}/requests`;

        await expect(calendarLink).toBeVisible({ timeout: 15_000 });
        await expect(requestsLink).toBeVisible();
        await expect(calendarLink).toHaveAttribute("href", calendarHref);
        await expect(requestsLink).toHaveAttribute("href", requestsHref);
        expect(calendarHref).not.toBe(requestsHref);

        await calendarLink.click();
        await expect(page).toHaveURL(new RegExp(`${calendarHref}$`));
        await expect(page.getByRole("heading", { level: 1, name: role.calendarHeading, exact: true })).toBeVisible();
        await expect(page.getByRole("heading", { level: 1, name: role.requestsHeading, exact: true })).toHaveCount(0);
        if (viewport.name === "desktop") {
          await expect(navigation.getByRole("link", { name: "Календарь", exact: true })).toHaveAttribute(
            "aria-current",
            "page",
          );
        }

        await navigation.getByRole("link", { name: "Заявки", exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`${requestsHref}$`));
        await expect(page.getByRole("heading", { level: 1, name: role.requestsHeading, exact: true })).toBeVisible();
        await expect(page.getByRole("heading", { level: 1, name: role.calendarHeading, exact: true })).toHaveCount(0);
        if (viewport.name === "desktop") {
          await expect(navigation.getByRole("link", { name: "Заявки", exact: true })).toHaveAttribute(
            "aria-current",
            "page",
          );
        }
      });
    }
  }
});
