import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth } from "./helpers";

const ROLES = [
  {
    kind: "customer",
    label: "Заказчик",
    cabinet: /\/cabinet\/customer/,
    heading: "Привет, E2E!",
    readinessRegion: "Онбординг",
    readinessItem: "Создать событие: город, дата и тип",
    nextAction: "Создать событие",
    nextHref: "/events/new",
  },
  {
    kind: "artist",
    label: "Артист / менеджер",
    cabinet: /\/cabinet\/performer/,
    heading: "Кабинет артиста",
    readinessRegion: "Профиль",
    readinessItem: "Профиль в каталоге",
    nextAction: "Настроить доступность →",
    nextHref: "/cabinet/performer/calendar",
  },
  {
    kind: "venue",
    label: "Площадка",
    cabinet: /\/cabinet\/venue/,
    heading: "Кабинет площадки",
    readinessRegion: "Профиль",
    readinessItem: "Площадка в каталоге",
    nextAction: "Управлять залами",
    nextHref: "/cabinet/venue/halls",
  },
] as const;

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "390px", width: 390, height: 844 },
] as const;

test.describe("W2-ONBOARD role entry §5", () => {
  test.setTimeout(90_000);

  for (const viewport of VIEWPORTS) {
    for (const role of ROLES) {
      test(`register ${role.kind} on ${viewport.name} → role cabinet + readiness checklist`, async ({
        page,
        request,
      }) => {
        test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
        await page.setViewportSize(viewport);

        const suffix = `${Date.now()}-${viewport.name}-${role.kind}`;
        const email = `e2e-onboard-${suffix}@booker.test`;

        await page.goto("/login");
        await page.getByRole("button", { name: "Создать аккаунт" }).click();
        await expect(page.getByTestId("role-picker")).toBeVisible();

        await page.getByTestId(`role-option-${role.kind}`).click();
        await page.locator('input[name="full_name"]').fill(`E2E ${role.label}`);
        await page.locator('input[name="email"]').fill(email);
        await page.locator('input[name="password"]').fill("password1");
        await page.locator("#accept_offer").check();
        await page.locator("#accept_privacy").check();
        await page.getByRole("button", { name: "Создать аккаунт" }).click();

        await expect(page).toHaveURL(role.cabinet, { timeout: 20_000 });
        const main = page.getByRole("main");
        await expect(main.getByRole("heading", { level: 1, name: role.heading, exact: true })).toBeVisible({
          timeout: 15_000,
        });

        const readiness = main.getByRole("region", { name: role.readinessRegion, exact: true });
        await expect(readiness).toBeVisible();
        await expect(readiness.getByRole("listitem").filter({ hasText: role.readinessItem })).toBeVisible();
        if (role.kind !== "customer") {
          await expect(readiness.getByRole("progressbar", { name: "Полнота профиля" })).toBeVisible();
        }

        await expect(main.getByRole("link", { name: role.nextAction, exact: true })).toHaveAttribute(
          "href",
          role.nextHref,
        );
      });
    }
  }

  for (const viewport of VIEWPORTS) {
    test(`register with safe next returns to internal path on ${viewport.name}`, async ({ page, request }) => {
      test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
      await page.setViewportSize(viewport);

      const email = `e2e-onboard-next-${Date.now()}-${viewport.name}@booker.test`;
      await page.goto("/login?next=%2Fsearch%3Fcity%3D%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0");
      await page.getByRole("button", { name: "Создать аккаунт" }).click();
      await page.getByTestId("role-option-customer").click();
      await page.locator('input[name="full_name"]').fill("E2E Next Customer");
      await page.locator('input[name="email"]').fill(email);
      await page.locator('input[name="password"]').fill("password1");
      await page.locator("#accept_offer").check();
      await page.locator("#accept_privacy").check();
      await page.getByRole("button", { name: "Создать аккаунт" }).click();

      await expect(page).toHaveURL(/\/search/, { timeout: 20_000 });
    });
  }
});
