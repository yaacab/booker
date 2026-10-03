import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { API_BASE, DEMO_ACCOUNTS, injectSession, login, register } from "./helpers";
import { demoTotp } from "./totp-fixture";

function proveTestMailboxAndSeedTotp(email: string) {
  const databaseUrl = process.env.BOOKER_DATABASE_URL || "";
  if (process.env.BOOKER_RUNTIME_ENV !== "test" || !databaseUrl.startsWith("sqlite:////tmp/")) {
    throw new Error("Operator E2E fixture requires isolated test SQLite");
  }
  const dbPath = databaseUrl.slice("sqlite:///".length);
  execFileSync("../api/.venv/bin/python", ["-c", `
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
try:
    from booker_api.totp_storage import encrypt_totp_secret
    db.execute("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP, totp_enabled = 1, totp_secret = ? WHERE email = ?", (encrypt_totp_secret(sys.argv[3]), sys.argv[2]))
    if db.total_changes != 1:
        raise RuntimeError("operator fixture account missing")
    db.commit()
finally:
    db.close()
`, dbPath, email, "JBSWY3DPEHPK3PXP"], { cwd: process.cwd() });
}

test("operator cabinet guards auth, role, enrollment and session changes", async ({ page }) => {
  await page.route("**/me", (route) => {
    const token = route.request().headers().authorization;
    if (token === "Bearer ordinary") return route.fulfill({ json: { id: "customer", is_support_operator: false } });
    if (token === "Bearer forbidden") return route.fulfill({ status: 403, json: { detail: "Forbidden" } });
    if (token === "Bearer enrollment") return route.fulfill({ json: { id: "pavel", is_support_operator: true, totp_enabled: false } });
    if (token === "Bearer operator") return route.fulfill({ json: { id: "pavel", is_support_operator: true, totp_enabled: true } });
    return route.fulfill({ status: 401, json: { detail: "Unauthorized" } });
  });
  await page.goto("/operator");
  await expect(page.locator("main").getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login?next=%2Foperator");
  await expect(page.getByRole("region", { name: "Очередь поддержки" })).toHaveCount(0);

  await page.evaluate(() => { localStorage.setItem("booker.token", "forbidden"); window.dispatchEvent(new Event("booker:session-changed")); });
  await expect(page.getByText("Нет доступа к кабинету оператора.")).toContainText("Нет доступа");
  await page.evaluate(() => { localStorage.setItem("booker.token", "ordinary"); window.dispatchEvent(new Event("booker:session-changed")); });
  await expect(page.getByText("Нет доступа к кабинету оператора.")).toContainText("Нет доступа");
  await page.evaluate(() => { localStorage.setItem("booker.token", "enrollment"); window.dispatchEvent(new Event("booker:session-changed")); });
  await expect(page.getByRole("link", { name: "Перейти к настройке" })).toHaveAttribute("href", "/login?next=%2Foperator&enroll=1");

  await page.evaluate(() => { localStorage.setItem("booker.token", "operator"); window.dispatchEvent(new Event("booker:session-changed")); });
  await expect(page.getByRole("region", { name: "Очередь поддержки" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Воронка пилота" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Риск" })).toHaveCount(0);
  await page.evaluate(() => { localStorage.removeItem("booker.token"); window.dispatchEvent(new Event("booker:session-changed")); });
  await expect(page.getByRole("region", { name: "Очередь поддержки" })).toHaveCount(0);
  await expect(page.locator("main").getByRole("link", { name: "Войти" })).toBeVisible();
  await page.evaluate(() => { localStorage.setItem("booker.token", "enrollment"); window.dispatchEvent(new Event("booker:session-changed")); });
  await page.getByRole("link", { name: "Перейти к настройке" }).click();
  await expect(page).toHaveURL(/\/login\?next=%2Foperator&enroll=1$/);
  await expect(page.getByRole("heading", { name: "Настроить второй фактор оператора" })).toBeVisible();
  await expect(page.getByLabel("Email оператора")).toBeVisible();
});

test("operator login reaches own cabinet without a workspace and profile exposes its link", async ({ page }) => {
  await page.route("**/legal/pack", (route) => route.fulfill({ json: { registration_available: false, documents: [] } }));
  await page.route("**/auth/login", (route) => route.fulfill({ json: { token: "operator", is_support_operator: true } }));
  await page.route("**/me", (route) => route.fulfill({ json: {
    id: "pavel", full_name: "Павел", email: "pavel@booker.test", is_support_operator: true,
    totp_enabled: true, organizations: [],
  } }));
  await page.goto("/login");
  await page.getByRole("textbox", { name: "Email" }).fill("pavel@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.getByRole("textbox", { name: "Код из приложения-аутентификатора" }).fill("123456");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/operator$/);
  await expect(page.getByRole("region", { name: "Очередь поддержки" })).toBeVisible();
  await page.goto("/profile");
  await expect(page.getByRole("link", { name: "Кабинет оператора поддержки" })).toHaveAttribute("href", "/operator");
  await expect(page.getByRole("link", { name: "Пульт. Без нейронки." })).toHaveCount(0);
});

test("email verification redirects operator to own cabinet", async ({ page }) => {
  await page.route("**/legal/pack", (route) => route.fulfill({ json: { registration_available: false, documents: [] } }));
  await page.route("**/auth/login", (route) => route.fulfill({ json: { token: "operator", is_support_operator: true } }));
  await page.route("**/auth/email-verification/confirm", (route) => route.fulfill({ json: { email_verified: true } }));
  await page.route("**/me", (route) => route.fulfill({ json: {
    id: "pavel", is_support_operator: true, totp_enabled: true, organizations: [],
  } }));
  const legalPackLoaded = page.waitForResponse("**/legal/pack");
  await page.goto("/login#verify=proof-token");
  await legalPackLoaded;
  await expect(page).toHaveURL(/\/login$/);
  const emailInput = page.getByRole("textbox", { name: "Email" });
  await emailInput.fill("pavel@booker.test");
  await page.getByLabel("Пароль", { exact: true }).fill("password1");
  await page.getByRole("textbox", { name: "Код из приложения, если включён второй фактор" }).fill("123456");
  await expect(emailInput).toHaveValue("pavel@booker.test");
  await page.getByRole("button", { name: "Подтвердить адрес" }).click();
  await expect(page).toHaveURL(/\/operator$/);
});

test("real API grant gives Pavel only the support queue and revocation ends access", async ({ page, request }) => {
  test.skip(process.env.BOOKER_RUNTIME_ENV !== "test" ||
    !process.env.BOOKER_DATABASE_URL?.startsWith("sqlite:////tmp/"),
  "requires isolated test SQLite");
  test.setTimeout(120_000);
  const email = `pavel-e2e-${Date.now()}@booker.test`;
  const operator = await register(request, email, "Павел");
  proveTestMailboxAndSeedTotp(email);
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  const adminHeaders = () => ({ Authorization: `Bearer ${admin.token}`, "X-Booker-TOTP": demoTotp() });
  const role = await request.post(`${API_BASE}/admin/support/operators`, {
    headers: adminHeaders(), data: { email, enabled: true },
  });
  expect(role.status(), await role.text()).toBe(200);
  const oldSession = await request.get(`${API_BASE}/me`, {
    headers: { Authorization: `Bearer ${operator.token}` },
  });
  expect(oldSession.status()).toBe(401);
  const signedIn = await request.post(`${API_BASE}/auth/login`, {
    data: { email, password: "password1", totp: demoTotp() },
  });
  expect(signedIn.status(), await signedIn.text()).toBe(200);
  const token = (await signedIn.json() as { token: string }).token;
  expect((await request.get(`${API_BASE}/admin/metrics`, {
    headers: { Authorization: `Bearer ${token}`, "X-Booker-TOTP": demoTotp() },
  })).status()).toBe(403);
  expect((await request.post(`${API_BASE}/orgs`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: "Запрещено", kind: "customer", city: "Москва" },
  })).status()).toBe(403);

  const customer = await login(request, DEMO_ACCOUNTS.customer);
  const ticket = await request.post(`${API_BASE}/support/tickets`, {
    headers: { Authorization: `Bearer ${customer.token}`, "Idempotency-Key": `operator-e2e-${Date.now()}` },
    data: { category: "technical", subject: "Нужен оператор", body: "Помогите с кабинетом" },
  });
  expect(ticket.status(), await ticket.text()).toBe(201);
  const ticketId = (await ticket.json() as { id: string }).id;
  await injectSession(page, token, "");
  await page.goto("/operator");
  const queue = page.getByRole("region", { name: "Очередь поддержки" });
  await expect(queue).toBeVisible();
  await expect(page.getByRole("link", { name: "Создать заявку" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Сделки" })).toHaveCount(0);
  await queue.getByLabel("Код 2FA").fill(demoTotp());
  await queue.getByRole("button", { name: "Показать очередь" }).click();
  const ticketNumber = `SUP-${ticketId.slice(0, 8).toUpperCase()}`;
  await queue.getByRole("button", { name: new RegExp(ticketNumber) }).click();
  await expect(queue.getByRole("heading", { name: new RegExp(ticketNumber) })).toBeVisible();
  await queue.getByLabel("Ответ пользователю").fill("Павел проверяет обращение");
  await queue.getByRole("button", { name: "Отправить ответ" }).click();
  await expect(queue.getByText("Ответ отправлен пользователю.")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await queue.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
  const revoke = await request.post(`${API_BASE}/admin/support/operators`, {
    headers: adminHeaders(), data: { email, enabled: false },
  });
  expect(revoke.status(), await revoke.text()).toBe(200);
  await page.reload();
  await expect(page.getByRole("link", { name: "Войти" })).toBeVisible();
  await expect(queue).toHaveCount(0);
});
