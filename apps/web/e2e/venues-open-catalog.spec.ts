import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, login } from "./helpers";

test("исследовательский импорт закрыт для гостя", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

  const catalog = await request.get(
    `${API_BASE}/catalog/demo/venues?city=${encodeURIComponent("Москва")}&limit=300`,
  );
  expect(catalog.status()).toBe(401);

  await page.goto("/investor/venues");
  await expect(page.getByRole("heading", { name: "Исследовательские площадки" })).toBeVisible();
  await expect(page.getByText(/витрина доступна только администратору/i)).toBeVisible();
  await expect(page.getByText("Показано 300 из 300")).toHaveCount(0);
});

test("администратор видит исследовательские карточки после входа", async ({ page, request }) => {
  test.setTimeout(60_000);
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  await page.addInitScript((token) => localStorage.setItem("booker.token", token), admin.token);
  await page.goto("/investor/venues");
  await expect(page.getByText("Показано 300 из 300")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/закрытая исследовательская витрина/i)).toBeVisible({ timeout: 15_000 });
});
