import { expect, test } from "@playwright/test";

const documentKeys = ["offer", "privacy", "consent_texts", "cookies", "disputes", "suppliers", "cancellation"];
const hashes = Object.fromEntries(documentKeys.map((key) => [key, "a".repeat(64)]));

async function mockLegalPack(page: import("@playwright/test").Page, registrationAvailable = false) {
  await page.route("**/legal/pack", (route) => route.fulfill({ json: registrationAvailable ? {
    pack_version: "test-1",
    status: "published",
    registration_available: true,
    acceptance_effect: "legal_acceptance",
    documents: documentKeys.map((key) => ({
      key, version: "test-1", content_hash: hashes[key], status: "published",
      required: ["offer", "privacy", "consent_texts"].includes(key), href: `/legal/${key === "consent_texts" ? "consent-texts" : key}`,
    })),
  } : { registration_available: false, documents: [] } }));
  if (registrationAvailable) {
    await page.route("**/api/legal/visible-hashes", (route) => route.fulfill({ json: { hashes } }));
  }
}

test("admin retries with authenticator code; failed login leaves no session", async ({ page }) => {
  const requests: Record<string, unknown>[] = [];
  const headers: Array<string | undefined> = [];
  await mockLegalPack(page);
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("login-totp-seeded")) {
      localStorage.setItem("booker.token", "old-session");
      localStorage.setItem("booker.admin", "1");
      sessionStorage.setItem("login-totp-seeded", "1");
    }
  });
  await page.route("**/auth/login", (route) => {
    requests.push(route.request().postDataJSON() as Record<string, unknown>);
    headers.push(route.request().headers().authorization);
    return route.fulfill(requests.length === 1
      ? { status: 401, json: { detail: "Нужен код второго фактора" } }
      : { json: { token: "fresh-admin-session", is_platform_admin: true } });
  });
  await page.route("**/me", (route) => route.fulfill({ json: { id: "admin-e2e", organizations: [] } }));

  await page.goto("/login?next=%2Fadmin");
  const code = page.getByRole("textbox", { name: "Код из приложения-аутентификатора" });
  await expect(code).toBeVisible();
  await expect(code).not.toHaveAttribute("required");
  await page.getByRole("textbox", { name: "Email" }).fill("admin@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.getByRole("button", { name: "Войти", exact: true }).click();

  await expect(page.locator("form [role='alert']")).toHaveText(
    "Нужен шестизначный код из приложения-аутентификатора. Введите его и повторите вход.",
  );
  expect(requests).toEqual([{ email: "admin@booker.test", password: "password1" }]);
  expect(headers).toEqual([undefined]);
  expect(await page.evaluate(() => ({ token: localStorage.getItem("booker.token"), admin: localStorage.getItem("booker.admin") })))
    .toEqual({ token: null, admin: null });

  await code.fill("123456");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  expect(requests[1]).toEqual({ email: "admin@booker.test", password: "password1", totp: "123456" });
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBe("fresh-admin-session");
});

test("ordinary login succeeds without a code", async ({ page }) => {
  const requests: Record<string, unknown>[] = [];
  await mockLegalPack(page);
  await page.route("**/auth/login", (route) => {
    requests.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: { token: "customer-session", is_platform_admin: false } });
  });
  await page.route("**/me", (route) => route.fulfill({ json: { organizations: [{ id: "customer-org", kind: "customer" }] } }));

  await page.goto("/login");
  await page.getByRole("textbox", { name: "Email" }).fill("customer@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.getByRole("button", { name: "Войти", exact: true }).click();

  await expect(page).toHaveURL(/\/cabinet\/customer$/);
  expect(requests).toEqual([{ email: "customer@booker.test", password: "password1" }]);
});

test("staff offline recovery requires a saved code and shows a new kit once", async ({ page }) => {
  const attempts: Record<string, unknown>[] = [];
  await mockLegalPack(page);
  await page.route("**/auth/admin-totp/recover", (route) => {
    attempts.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill(attempts.length === 1
      ? { status: 403, json: { detail: "Подтверждение недействительно" } }
      : { json: { totp_enabled: true, recovery_codes: Array.from({ length: 10 }, (_, i) => `new-kit-${i + 1}`) } });
  });

  await page.goto("/login");
  await page.getByRole("button", { name: "Потеряли Authenticator?" }).click();
  await expect(page.getByRole("heading", { name: "Восстановить второй фактор" })).toBeVisible();
  const secret = await page.getByLabel("Новый секрет TOTP").inputValue();
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await page.getByLabel("Email", { exact: true }).fill("sole-admin@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.getByLabel("Сохранённый резервный код").fill("1111-2222-3333-4444-5555-6666");
  await page.getByLabel("Текущий код нового приложения").fill("123456");
  await page.getByRole("button", { name: "Восстановить доступ" }).click();
  await expect(page.locator("form [role='alert']")).toContainText("Подтверждение недействительно");
  await page.getByLabel("Текущий код нового приложения").fill("654321");
  await page.getByRole("button", { name: "Восстановить доступ" }).click();
  await expect(page.getByRole("textbox", { name: "Новые резервные коды" })).toHaveValue(/new-kit-1/);
  await expect(page.getByRole("button", { name: "Перейти ко входу" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "Я сохранил новые коды вне Букера" }).check();
  await page.getByRole("button", { name: "Перейти ко входу" }).click();
  await expect(page.getByRole("heading", { name: "Войти в Букер" })).toBeVisible();
  expect(attempts).toEqual([
    { email: "sole-admin@booker.test", password: "password1", recovery_code: "1111-2222-3333-4444-5555-6666", secret, code: "123456" },
    { email: "sole-admin@booker.test", password: "password1", recovery_code: "1111-2222-3333-4444-5555-6666", secret, code: "654321" },
  ]);
});

test("registration and recovery omit TOTP; admin reset can send its own code", async ({ page }) => {
  const registerBodies: Record<string, unknown>[] = [];
  const recoveryBodies: Record<string, unknown>[] = [];
  const resetBodies: Record<string, unknown>[] = [];
  await mockLegalPack(page, true);
  await page.route("**/auth/register", (route) => {
    registerBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ status: 400, json: { detail: "Registration checked" } });
  });
  await page.route("**/auth/recover", (route) => {
    recoveryBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: {} });
  });
  await page.route("**/auth/recover/confirm", (route) => {
    resetBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: {} });
  });

  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Создать аккаунт" })).toBeEnabled();
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.getByRole("textbox", { name: "Код из приложения-аутентификатора" })).toHaveCount(0);
  await page.getByLabel("Имя").fill("Тестовый пользователь");
  await page.getByRole("textbox", { name: "Email" }).fill("register@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.locator("#accept_offer").check();
  await page.locator("#accept_privacy").check();
  await page.locator("#accept_consent_texts").check();
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.locator("form [role='alert']")).toHaveText("Registration checked");
  expect(registerBodies).toHaveLength(1);
  expect(registerBodies[0]).not.toHaveProperty("totp");

  await page.getByRole("button", { name: "Вернуться ко входу" }).click();
  await page.getByRole("button", { name: "Забыли пароль?" }).click();
  await expect(page.getByRole("textbox", { name: "Код из приложения-аутентификатора" })).toHaveCount(0);
  await page.getByRole("textbox", { name: "Email" }).fill("recover@booker.test");
  await page.getByRole("button", { name: "Отправить инструкцию" }).click();
  await expect(page.getByText("Если аккаунт существует", { exact: false })).toBeVisible();
  expect(recoveryBodies).toEqual([{ email: "recover@booker.test" }]);

  await page.goto("/login?reset=reset-token");
  await expect(page.getByRole("heading", { name: "Задайте новый пароль" })).toBeVisible();
  await page.getByRole("textbox", { name: "Код из приложения-аутентификатора" }).fill("123456");
  await page.getByLabel("Новый пароль").fill("newpassword1");
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByText("Пароль обновлён. Войдите с новым паролем.")).toBeVisible();
  expect(resetBodies).toEqual([{ token: "reset-token", password: "newpassword1", totp: "123456" }]);
});
