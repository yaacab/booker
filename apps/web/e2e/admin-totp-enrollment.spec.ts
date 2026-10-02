import { expect, test } from "@playwright/test";

test("admin opens pre-login TOTP setup, confirms email proof, then signs in again", async ({ page }) => {
  const challenges: Record<string, unknown>[] = [];
  const confirmations: Record<string, unknown>[] = [];

  await page.addInitScript(() => {
    if (!sessionStorage.getItem("admin-totp-test-seeded")) {
      localStorage.setItem("booker.token", "old-admin-session");
      localStorage.setItem("booker.admin", "1");
      sessionStorage.setItem("admin-totp-test-seeded", "1");
    }
  });
  await page.route("**/me", (route) => route.fulfill({ json: { id: "operator-e2e", totp_enabled: false } }));
  await page.route("**/admin/verifications", (route) => route.fulfill({ json: { queue: [], artists: [], venues: [] } }));
  await page.route("**/admin/audit", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/admin/metrics", (route) => route.fulfill({ json: { periods: { "7": {}, "30": {} } } }));
  await page.route("**/admin/venue-catalog/venues?limit=50", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/admin/venue-catalog/report", (route) => route.fulfill({
    json: { total: 0, automated: 0, unverified: 0, verified: 0, partners: 0, published: 0, needs_review: 0 },
  }));
  await page.route("**/admin/disputes", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/legal/pack", (route) => route.fulfill({ json: { registration_available: false, documents: [] } }));
  await page.route("**/auth/admin-totp/challenge", (route) => {
    challenges.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: { ok: true } });
  });
  await page.route("**/auth/admin-totp/confirm", (route) => {
    confirmations.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill(confirmations.length === 1
      ? { status: 403, json: { detail: "Подтверждение недействительно" } }
      : { json: { totp_enabled: true, recovery_codes: Array.from({ length: 10 }, (_, i) => `code-${i + 1}`) } });
  });

  await page.goto("/admin");
  await page.getByRole("link", { name: "Перейти к настройке" }).click();
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin&enroll=1$/);
  expect(await page.evaluate(() => ({
    token: localStorage.getItem("booker.token"), admin: localStorage.getItem("booker.admin"),
  }))).toEqual({ token: null, admin: null });

  await page.getByLabel("Email администратора").fill("admin@booker.test");
  await page.getByLabel("Пароль администратора").fill("password1");
  await page.getByRole("button", { name: "Получить подтверждение по почте" }).click();
  expect(challenges).toEqual([{ email: "admin@booker.test", password: "password1" }]);
  const secret = await page.getByLabel("Секрет TOTP для приложения").inputValue();
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await page.getByLabel("Код подтверждения из письма").fill("p".repeat(43));
  await page.getByLabel("Повторите пароль администратора").fill("password1");
  await page.getByLabel("Текущий код из приложения").fill("123456");
  await page.getByRole("button", { name: "Включить второй фактор" }).click();
  await expect(page.locator("form [role='alert']")).toContainText("Подтверждение недействительно");
  expect(confirmations[0]).toEqual({
    email: "admin@booker.test", password: "password1", proof: "p".repeat(43), secret, code: "123456",
  });
  await page.getByLabel("Текущий код из приложения").fill("654321");
  await page.getByRole("button", { name: "Включить второй фактор" }).click();
  await expect(page.getByText("Второй фактор включён. Сохраните резервные коды", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Резервные коды", { exact: true })).toHaveValue(/code-1/);
  await expect(page.getByRole("button", { name: "Перейти ко входу" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "Я сохранил коды вне Букера" }).check();
  await page.getByRole("button", { name: "Перейти ко входу" }).click();
  await expect(page.getByRole("heading", { name: "Войти в Букер" })).toBeVisible();
  expect(confirmations[1]).toEqual({ ...confirmations[0], code: "654321" });
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBeNull();
  await expect(page).not.toHaveURL(/secret=|proof=/);
});
