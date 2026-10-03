import { createHmac } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

const BOT_TOKEN = "test-telegram-fixture-token-20261003";

function initData(queryId: string, userId = 91827364): string {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: queryId,
    user: JSON.stringify({ id: userId, first_name: "Телеграм", last_name: "Тест" }),
  };
  const check = Object.keys(fields).sort().map((key) => `${key}=${fields[key]}`).join("\n");
  const secret = createHmac("sha256", "WebAppData").update(BOT_TOKEN).digest();
  fields.hash = createHmac("sha256", secret).update(check).digest("hex");
  return new URLSearchParams(fields).toString();
}

async function mockTelegram(page: Page, raw: string) {
  await page.route("**/telegram-web-app.js?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/javascript",
      body: `window.Telegram={WebApp:{initData:${JSON.stringify(raw)},ready(){},expand(){}}};`,
    });
  });
}

test("Mini App first login records draft consent, then returns to the same Booker account", async ({ page, request }) => {
  await mockTelegram(page, initData("booker-first-login"));
  await page.goto("/telegram");
  await expect(page.getByRole("heading", { name: "Первый вход в Букер" })).toBeVisible();
  await expect(page.getByText("регистрация тестовая", { exact: false })).toBeVisible();
  await page.getByLabel("Ознакомлен(а) с черновиком оферты").check();
  await page.getByLabel("Ознакомлен(а) с политикой").check();
  await page.getByLabel("Ознакомлен(а) с черновиком согласий").check();
  await page.getByLabel("Понимаю, что документы черновые и регистрация тестовая.").check();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await expect(page.getByRole("heading", { name: "Создайте рабочее пространство" })).toBeVisible();
  await page.getByLabel("Название пространства").fill("Тестовое событие Telegram");
  await page.getByLabel("Кто вы?").selectOption("customer");
  await page.getByRole("button", { name: "Создать пространство" }).click();
  await expect(page).toHaveURL(/\/cabinet\/customer/);
  const firstToken = await page.evaluate(() => localStorage.getItem("booker.token"));
  expect(firstToken).toBeTruthy();
  const apiUrl = process.env.BOOKER_API_URL;
  if (!apiUrl || !firstToken) throw new Error("Isolated API URL and Booker token required");
  const me = await request.get(`${apiUrl}/me`, { headers: { Authorization: `Bearer ${firstToken}` } });
  expect(me.ok()).toBeTruthy();
  const firstUser = await me.json() as { id: string; email: string | null };
  expect(firstUser.email).toBeNull();

  await page.unrouteAll();
  await mockTelegram(page, initData("booker-return-login"));
  await page.goto("/telegram");
  await expect(page).toHaveURL(/\/cabinet\/customer/);
  const secondToken = await page.evaluate(() => localStorage.getItem("booker.token"));
  expect(secondToken).toBeTruthy();
  const returning = await request.get(`${apiUrl}/me`, { headers: { Authorization: `Bearer ${secondToken}` } });
  expect(returning.ok()).toBeTruthy();
  expect((await returning.json() as { id: string }).id).toBe(firstUser.id);
});

test("ordinary browser shows a real Mini App boundary", async ({ page }) => {
  await mockTelegram(page, "");
  await page.goto("/telegram");
  await expect(page.getByText("Откройте Букер из Telegram Mini App")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBeNull();
});

test("tampered initData cannot create a Booker session", async ({ page }) => {
  const bad = initData("tampered").replace("91827364", "91827365");
  await mockTelegram(page, bad);
  await page.goto("/telegram");
  await expect(page.getByText("Данные Telegram недействительны", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBeNull();
});

test("Mini App waits for mailbox proof before offering a workspace", async ({ page }) => {
  await mockTelegram(page, initData("telegram-mailbox", 91827366));
  let verified = false;
  await page.route("**/me", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: {
      ...body,
      email: verified ? "telegram-owner@booker.test" : null,
      email_verified: verified,
      email_verification_required: !verified,
    } });
  });
  await page.route("**/me/email/telegram/request", async (route) => {
    const body = route.request().postDataJSON() as { email: string; init_data: string };
    expect(body.email).toBe("telegram-owner@booker.test");
    expect(body.init_data).toContain("hash=");
    await route.fulfill({ json: { ok: true, delivery: "sent" } });
  });
  await page.goto("/telegram");
  await expect(page.getByRole("heading", { name: "Первый вход в Букер" })).toBeVisible();
  await page.getByLabel("Ознакомлен(а) с черновиком оферты").check();
  await page.getByLabel("Ознакомлен(а) с политикой").check();
  await page.getByLabel("Ознакомлен(а) с черновиком согласий").check();
  await page.getByLabel("Понимаю, что документы черновые и регистрация тестовая.").check();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await expect(page.getByRole("heading", { name: "Подтвердите email" })).toBeVisible();
  await page.getByLabel("Email").fill("telegram-owner@booker.test");
  await page.getByRole("button", { name: "Отправить письмо" }).click();
  await expect(page.getByRole("heading", { name: "Проверьте почту" })).toBeVisible();
  await page.getByRole("button", { name: "Я подтвердил(а) адрес" }).click();
  await expect(page.getByText("Адрес пока не подтверждён", { exact: false })).toBeVisible();
  verified = true;
  await page.getByRole("button", { name: "Я подтвердил(а) адрес" }).click();
  await expect(page.getByRole("heading", { name: "Создайте рабочее пространство" })).toBeVisible();
});

test("mailbox link confirms without granting a Booker session", async ({ page }) => {
  await page.route("**/auth/email-verification/external-confirm", async (route) => {
    const body = route.request().postDataJSON() as { token: string };
    expect(body.token).toBe("a".repeat(40));
    expect(route.request().headers().authorization).toBeUndefined();
    await route.fulfill({ json: { email_verified: true, idempotent: false } });
  });
  await page.goto(`/verify-email#verify=${"a".repeat(40)}`);
  await expect(page.getByText("Адрес подтверждён", { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/\/verify-email$/);
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBeNull();
});
