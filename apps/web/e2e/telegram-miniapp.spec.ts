import { createHmac } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

const BOT_TOKEN = "test-telegram-fixture-token-20261003";

function initData(queryId: string): string {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: queryId,
    user: JSON.stringify({ id: 91827364, first_name: "Телеграм", last_name: "Тест" }),
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
