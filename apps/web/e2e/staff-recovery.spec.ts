import { expect, test } from "@playwright/test";
import { API_BASE } from "./helpers";
import { demoTotp, fixtureTotp } from "./totp-fixture";

test("sole admin regenerates a kit and recovers through the real API on mobile", async ({ page, request }) => {
  test.skip(process.env.BOOKER_E2E_STAFF_RECOVERY_ISOLATED !== "1",
    "Recovery mutates the admin factor; run this scenario in its own temporary database");
  if (process.env.BOOKER_RUNTIME_ENV !== "test" ||
      !process.env.BOOKER_DATABASE_URL?.startsWith("sqlite:////tmp/")) {
    throw new Error("Recovery E2E requires isolated temporary test SQLite");
  }
  const credentials = { email: "admin@booker.test", password: "password1" };
  const login = await request.post(`${API_BASE}/auth/login`, {
    data: { ...credentials, totp: demoTotp() },
  });
  expect(login.status()).toBe(200);
  const { token } = await login.json();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.evaluate((value) => localStorage.setItem("booker.token", value), token);
  await page.goto("/profile");
  await page.getByLabel("Текущий код Authenticator", { exact: true }).fill(demoTotp());
  await page.getByRole("button", { name: "Проверить количество" }).click();
  await expect(page.getByText("Осталось кодов: 0", { exact: true })).toBeVisible();
  await page.getByLabel("Пароль для выпуска нового комплекта").fill(credentials.password);
  await page.getByRole("button", { name: "Создать новые резервные коды" }).click();
  const kit = (await page.getByLabel("Новый комплект", { exact: true }).inputValue()).split("\n");
  expect(kit).toHaveLength(10);
  expect((await request.get(`${API_BASE}/me`, { headers: { Authorization: `Bearer ${token}` } })).status()).toBe(401);
  await page.getByRole("checkbox", { name: "Я сохранил коды", exact: true }).check();
  await page.getByRole("button", { name: "Войти заново" }).click();
  await page.getByRole("button", { name: "Потеряли Authenticator?" }).click();
  const secret = await page.getByLabel("Новый секрет TOTP", { exact: true }).inputValue();
  await page.getByLabel("Email", { exact: true }).fill(credentials.email);
  await page.getByLabel("Пароль", { exact: true }).fill(credentials.password);
  await page.getByLabel("Сохранённый резервный код").fill(kit[0]);
  await page.getByLabel("Текущий код нового приложения").fill(fixtureTotp(secret));
  await page.getByRole("button", { name: "Восстановить доступ" }).click();
  const newKit = (await page.getByRole("textbox", { name: "Новые резервные коды" }).inputValue()).split("\n");
  expect(newKit).toHaveLength(10);
  expect(newKit.some((code) => kit.includes(code))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("checkbox", { name: "Я сохранил новые коды вне Букера" }).check();
  await page.getByRole("button", { name: "Перейти ко входу" }).click();
  await page.getByLabel("Email", { exact: true }).fill(credentials.email);
  await page.getByLabel("Пароль", { exact: true }).fill(credentials.password);
  await page.getByRole("textbox", { name: "Код из приложения-аутентификатора" }).fill(fixtureTotp(secret));
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const replay = await request.post(`${API_BASE}/auth/admin-totp/recover`, {
    data: { ...credentials, recovery_code: kit[0], secret, code: fixtureTotp(secret) },
  });
  expect(replay.status()).toBe(403);
});
