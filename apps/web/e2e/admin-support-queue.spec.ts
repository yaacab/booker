import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { execFileSync } from "node:child_process";
import { API_BASE, DEMO_ACCOUNTS, fetchMe, injectSession, login, register } from "./helpers";

function adminTotp(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [..."JBSWY3DPEHPK3PXP"].map((char) => alphabet.indexOf(char).toString(2).padStart(5, "0")).join("");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => Number.parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  return ((digest.readUInt32BE(digest[digest.length - 1] & 15) & 0x7fffffff) % 1_000_000)
    .toString().padStart(6, "0");
}

test("ordinary user handoff reaches protected operator queue and returns one reply", async ({ page, request, browser }) => {
  test.setTimeout(120_000);
  const customer = await login(request, DEMO_ACCOUNTS.customer);
  const me = await fetchMe(request, customer.token);
  const orgId = me.organizations.find((item) => item.kind === "customer")!.id;
  const customerHeaders = { Authorization: `Bearer ${customer.token}`, "X-Booker-Org": orgId };
  const listTickets = async (): Promise<string[]> => {
    const res = await request.get(`${API_BASE}/support/tickets`, { headers: customerHeaders });
    expect(res.status()).toBe(200);
    return ((await res.json()) as { items: { id: string }[] }).items.map((item) => item.id);
  };
  const before = new Set(await listTickets());
  await injectSession(page, customer.token, orgId);
  await page.goto("/support");
  await page.getByLabel("Сообщение помощнику").fill("Мне нужен возврат оплаты");
  await page.getByRole("button", { name: "Спросить помощника" }).click();
  await page.getByRole("button", { name: "Передать человеку" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Передано человеку:" })).toBeVisible();
  const ticketIds = (await listTickets()).filter((id) => !before.has(id));
  expect(ticketIds).toHaveLength(1);
  const ticketId = ticketIds[0];
  const ticketNumber = `SUP-${ticketId.slice(0, 8).toUpperCase()}`;

  const denied = await request.get(`${API_BASE}/admin/support/tickets`, { headers: customerHeaders });
  expect(denied.status()).toBe(403);
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  await injectSession(adminPage, admin.token, "");
  await adminPage.goto("/admin");
  const targets = adminPage.getByRole("region", { name: "Дежурные адресаты поддержки" });
  await expect(targets).toBeVisible();
  await targets.getByLabel("Код 2FA для управления адресатами").fill(adminTotp());
  await targets.getByRole("button", { name: "Загрузить адресатов" }).click();
  await expect(targets.getByText("Telegram: отключён.", { exact: false })).toBeVisible();
  await targets.getByLabel("Сотрудник", { exact: true }).selectOption(admin.user_id);
  await targets.getByLabel("Канал", { exact: true }).selectOption("cabinet");
  await targets.getByRole("button", { name: "Включить адресата" }).click();
  await expect(targets.getByText(/Адресат включён/)).toBeVisible();
  const queue = adminPage.getByRole("region", { name: "Очередь поддержки" });
  await expect(queue).toBeVisible();
  const fillTotp = async () => queue.getByLabel("Код 2FA").fill(adminTotp());
  await fillTotp();
  await queue.getByRole("button", { name: "Показать очередь" }).click();
  await expect(queue.getByRole("button", { name: new RegExp(ticketNumber) })).toBeVisible();
  await queue.getByRole("button", { name: new RegExp(ticketNumber) }).click();
  await expect(queue.getByRole("heading", { name: new RegExp(ticketNumber) })).toBeFocused();
  await expect(queue.getByLabel("Контекст обращения")).toContainText("Передача из помощника Букера.");
  await fillTotp();
  await queue.getByRole("button", { name: "Взять в работу" }).click();
  await expect(queue.getByText("Назначение: мне")).toBeVisible();
  await expect(queue.getByText(/Принятие: подтверждено/)).toBeVisible();

  if (process.env.BOOKER_RUNTIME_ENV === "test" &&
      process.env.BOOKER_DATABASE_URL?.startsWith("sqlite:////tmp/")) {
    const colleagueEmail = `handoff-e2e-${Date.now()}@booker.test`;
    const colleague = await register(request, colleagueEmail, "Второй оператор");
    const databasePath = process.env.BOOKER_DATABASE_URL.slice("sqlite:///".length);
    execFileSync("../api/.venv/bin/python", ["-c", `
import sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path("../api").resolve()))
from booker_api.totp_storage import encrypt_totp_secret
with sqlite3.connect(sys.argv[1]) as db:
    db.execute("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP, totp_enabled = 1, totp_secret = ? WHERE email = ?", (encrypt_totp_secret(sys.argv[3]), sys.argv[2]))
    if db.total_changes != 1:
        raise RuntimeError("isolated handoff fixture missing")
`, databasePath, colleagueEmail, "JBSWY3DPEHPK3PXP"], { cwd: process.cwd() });
    const granted = await request.post(`${API_BASE}/admin/support/operators`, {
      headers: { Authorization: `Bearer ${admin.token}`, "X-Booker-TOTP": adminTotp() },
      data: { email: colleagueEmail, enabled: true },
    });
    expect(granted.status(), await granted.text()).toBe(200);
    await fillTotp();
    await queue.getByRole("button", { name: "Показать очередь" }).click();
    await queue.getByRole("button", { name: new RegExp(ticketNumber) }).click();
    await queue.getByLabel("Передать обращение").selectOption(colleague.user_id);
    await fillTotp();
    await queue.getByRole("button", { name: "Передать", exact: true }).click();
    await expect(queue.getByText("Назначение: другому сотруднику")).toBeVisible();
    await expect(queue.getByText("Принятие: ожидается")).toBeVisible();
    await queue.getByLabel("Передать обращение").selectOption(admin.user_id);
    await fillTotp();
    await queue.getByRole("button", { name: "Передать", exact: true }).click();
    await expect(queue.getByText("Назначение: мне")).toBeVisible();
    await fillTotp();
    await queue.getByRole("button", { name: "Подтвердить принятие" }).click();
    await expect(queue.getByText(/Принятие: подтверждено/)).toBeVisible();
  }
  await queue.getByLabel("Приоритет очереди").selectOption("high");
  await fillTotp();
  await queue.getByRole("button", { name: "Сохранить приоритет" }).click();
  await expect(queue.getByText("Приоритет очереди обновлён. Срок первого ответа не изменился.")).toBeVisible();

  await fillTotp();
  await queue.getByLabel("Заметка для операторов").fill("Только внутренний контекст");
  await queue.getByRole("button", { name: "Сохранить заметку" }).click();
  await expect(queue.getByText("Внутренняя заметка сохранена.")).toBeVisible();
  await expect(queue.getByText("Только внутренний контекст")).toBeVisible();
  await fillTotp();
  await queue.getByLabel("Ответ пользователю").fill("Оператор проверяет обращение");
  const sendReply = queue.getByRole("button", { name: "Отправить ответ" });
  await expect(sendReply).toBeEnabled();
  await sendReply.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });
  await expect(queue.getByText("Ответ отправлен пользователю.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Оператор проверяет обращение")).toBeVisible();
  expect(await page.getByText("Оператор проверяет обращение").count()).toBe(1);
  await expect(page.getByText("Только внутренний контекст")).toHaveCount(0);

  await page.getByLabel("Ответ в поддержку").fill("Уточнение после ответа");
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
  await expect(page.getByText("Уточнение после ответа")).toBeVisible();
  await fillTotp();
  await queue.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(queue.getByRole("alert")).toContainText("Обращение изменилось");
  await fillTotp();
  await queue.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(queue.getByRole("button", { name: "Открыть повторно" })).toBeVisible();
  await fillTotp();
  await queue.getByRole("button", { name: "Открыть повторно" }).click();
  await expect(queue.getByRole("button", { name: "Закрыть", exact: true })).toBeVisible();
  await expect(queue.getByText("Принятие: ожидается")).toBeVisible();
  await fillTotp();
  await queue.getByRole("button", { name: "Подтвердить принятие" }).click();
  await expect(queue.getByText(/Принятие: подтверждено/)).toBeVisible();
  await adminPage.setViewportSize({ width: 390, height: 844 });
  const widths = await queue.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
  const targetWidths = await targets.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(targetWidths.scroll).toBeLessThanOrEqual(targetWidths.client + 2);
  await adminContext.close();
});
