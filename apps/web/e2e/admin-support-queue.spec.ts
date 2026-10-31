import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { API_BASE, DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

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

  await fillTotp();
  await queue.getByLabel("Заметка для операторов").fill("Только внутренний контекст");
  await queue.getByRole("button", { name: "Сохранить заметку" }).click();
  await expect(queue.getByText("Только внутренний контекст")).toBeVisible();
  await fillTotp();
  await queue.getByLabel("Ответ пользователю").fill("Оператор проверяет обращение");
  await queue.getByRole("button", { name: "Отправить ответ" }).evaluate((button: HTMLButtonElement) => {
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
  await adminPage.setViewportSize({ width: 390, height: 844 });
  const widths = await queue.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
  await adminContext.close();
});
