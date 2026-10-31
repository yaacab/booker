import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth } from "./helpers";

const ROLES = [
  {
    kind: "customer",
    label: "Заказчик",
    cabinet: /\/cabinet\/customer/,
    onboarding: "customer-onboarding",
  },
  {
    kind: "artist",
    label: "Артист / менеджер",
    cabinet: /\/cabinet\/performer/,
    onboarding: "performer-onboarding",
  },
  {
    kind: "venue",
    label: "Площадка",
    cabinet: /\/cabinet\/venue/,
    onboarding: "venue-onboarding",
  },
] as const;

test.describe("W2-ONBOARD role entry §5", () => {
  test.setTimeout(90_000);

  for (const role of ROLES) {
    test(`register ${role.kind} → ${role.cabinet} + onboarding checklist`, async ({
      page,
      request,
    }) => {
      test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

      const suffix = `${Date.now()}-${role.kind}`;
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
      await expect(page.getByTestId(role.onboarding)).toBeVisible({ timeout: 15_000 });
    });
  }

  test("register with safe next returns to internal path", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const email = `e2e-onboard-next-${Date.now()}@booker.test`;
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
});
