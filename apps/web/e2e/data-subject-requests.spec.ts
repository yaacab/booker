import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { API_BASE, DEMO_ACCOUNTS, injectSession, login } from "./helpers";

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

test("subject request stays private; operator hold blocks deletion and preserves history", async ({ page, request, browser }) => {
  test.setTimeout(120_000);
  const customer = await login(request, DEMO_ACCOUNTS.customer);
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  await injectSession(page, customer.token, "");
  await page.goto("/profile");
  const userSection = page.getByRole("region", { name: "Запросы по персональным данным" });
  await expect(userSection).toBeVisible();
  await userSection.getByLabel("Тип запроса").selectOption("delete");
  await userSection.getByRole("button", { name: "Отправить запрос" }).click();
  await expect(userSection.getByRole("status")).toContainText("Запрос получен");
  await expect(userSection.getByText("Статус: Получен")).toBeVisible();
  await expect(userSection.getByText("Юридическое удержание")).toHaveCount(0);
  const own = await request.get(`${API_BASE}/data-subject/requests`, {
    headers: { Authorization: `Bearer ${customer.token}` },
  });
  expect(own.status()).toBe(200);
  const items = (await own.json() as { items: { id: string; request_type: string }[] }).items;
  const requestId = items.find((item) => item.request_type === "delete")!.id;
  const denied = await request.get(`${API_BASE}/admin/data-subject/requests/${requestId}`, {
    headers: { Authorization: `Bearer ${customer.token}` },
  });
  expect(denied.status()).toBe(403);

  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  await injectSession(adminPage, admin.token, "");
  await adminPage.goto("/admin");
  const queue = adminPage.getByRole("region", { name: "Запросы по данным" });
  await expect(queue).toBeVisible();
  await queue.getByLabel("Код 2FA, если сессия ещё не подтверждена").fill(adminTotp());
  await queue.getByRole("button", { name: "Обновить очередь" }).click();
  await expect(queue.getByRole("button", { name: "Удаление данных · Получен" })).toBeVisible();
  await queue.getByRole("button", { name: "Удаление данных · Получен" }).click();
  await expect(queue.getByRole("region", { name: "Операторская карточка запроса" })).toBeVisible();
  await queue.getByRole("button", { name: "Изменить статус" }).click();
  await expect(queue.getByText("Статус: На рассмотрении")).toBeVisible();
  await queue.getByText("Юридическое удержание", { exact: true }).click();
  await queue.getByRole("button", { name: "Зарегистрировать удержание" }).click();
  await expect(queue.getByText("Действует юридическое удержание.")).toBeVisible();
  await queue.getByRole("button", { name: "Показать план удаления" }).click();
  await expect(queue.getByRole("region", { name: "План удаления" })).toContainText("Исполнение удаления через эту страницу недоступно");
  await expect(queue.getByLabel("Новый статус").locator("option[value='approved']")).toHaveCount(0);
  await queue.getByText("Юридическое удержание", { exact: true }).click();
  adminPage.once("dialog", (dialog) => void dialog.accept());
  await queue.getByRole("button", { name: "Снять удержание" }).click();
  await expect(queue.getByText("Действует юридическое удержание.")).toHaveCount(0);
  await queue.getByLabel("Новый статус").selectOption("approved");
  await queue.getByRole("button", { name: "Изменить статус" }).click();
  await expect(queue.getByText("Статус: Одобрен")).toBeVisible();
  await page.reload();
  await userSection.getByRole("button", { name: "Удаление данных · Объём рассмотрен, удаление не выполнено" }).click();
  await expect(userSection.getByText("Статус: Одобрен")).toBeVisible();
  await expect(userSection.getByText("Удаление данных не выполнено", { exact: false })).toBeVisible();
  await expect(userSection.getByRole("button", { name: "Отменить запрос" })).toHaveCount(0);
  await expect(userSection.getByText("Юридическое удержание")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await userSection.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
  let unblockFetch!: () => void;
  let fetchStarted!: () => void;
  const blocked = new Promise<void>((resolve) => { unblockFetch = resolve; });
  const started = new Promise<void>((resolve) => { fetchStarted = resolve; });
  await page.route("**/data-subject/requests?*", async (route) => {
    fetchStarted();
    await blocked;
    await route.continue();
  });
  const reloading = page.reload();
  await started;
  const another = await login(request, DEMO_ACCOUNTS.artist);
  const switchPage = await page.context().newPage();
  await injectSession(switchPage, another.token, "");
  await switchPage.goto("/profile");
  unblockFetch();
  await reloading;
  await page.unroute("**/data-subject/requests?*");
  await expect(userSection.getByText("Статус: Одобрен")).toHaveCount(0);
  await expect(userSection.getByRole("button", { name: "Удаление данных · Объём рассмотрен, удаление не выполнено" })).toHaveCount(0);
  await switchPage.close();
  await adminContext.close();
});
