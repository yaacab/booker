import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_PASSWORD } from "./helpers";

test.describe("public registration legal gate", () => {
  test.skip(
    process.env.BOOKER_PUBLIC_REGISTRATION_ENABLED !== "0",
    "Run with BOOKER_PUBLIC_REGISTRATION_ENABLED=0 against the closed-gate servers",
  );

  test("direct register URL and API stay closed while existing login works", async ({
    page,
    request,
  }) => {
    await page.goto("/login?mode=register&role=artist");

    await expect(page.getByRole("status")).toContainText("Саморегистрация временно закрыта");
    await expect(page.getByTestId("role-picker")).toHaveCount(0);
    await expect(page.locator('input[name="full_name"]')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Создать аккаунт" })).toHaveCount(0);

    const denied = await request.post(`${API_BASE}/auth/register`, {
      data: {
        email: `closed-${Date.now()}@booker.test`,
        password: DEMO_PASSWORD,
        full_name: "Публичная регистрация",
        accept_offer: true,
        accept_privacy: true,
      },
    });
    expect(denied.status()).toBe(403);
    await expect(denied.json()).resolves.toMatchObject({
      detail: expect.stringContaining("Саморегистрация временно закрыта"),
    });

    await page.getByLabel("Email", { exact: true }).fill("customer@booker.test");
    await page.getByLabel("Пароль", { exact: true }).fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: "Войти", exact: true }).click();
    await expect(page).toHaveURL(/\/cabinet\/customer/, { timeout: 20_000 });
  });
});

test.describe("public registration explicit opt-in", () => {
  test.skip(
    process.env.BOOKER_PUBLIC_REGISTRATION_ENABLED !== "1",
    "Run with BOOKER_PUBLIC_REGISTRATION_ENABLED=1 against the opt-in test servers",
  );

  test("explicit test flag keeps the local registration flow available", async ({ page }) => {
    await page.goto("/login?mode=register&role=customer");
    await expect(page.getByTestId("role-picker")).toBeVisible();

    await page.locator('input[name="full_name"]').fill("E2E явный opt-in");
    await page.locator('input[name="email"]').fill(`registration-opt-in-${Date.now()}@booker.test`);
    await page.locator('input[name="password"]').fill(DEMO_PASSWORD);
    await page.locator("#accept_offer").check();
    await page.locator("#accept_privacy").check();
    await page.getByRole("button", { name: "Создать аккаунт", exact: true }).click();

    await expect(page).toHaveURL(/\/cabinet\/customer/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Привет, E2E!" })).toBeVisible();
  });
});
