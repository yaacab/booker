import { expect, test } from "@playwright/test";

test("главная: бренд и поиск", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Букер" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Кто ещё не занят" })).toBeVisible();
});

test("юридический пакет опубликован как черновик", async ({ page }) => {
  await page.goto("/legal/offer");
  await expect(page.getByText("не действующая оферта")).toBeVisible();
  await expect(page.getByText("не является исполнителем выступления", { exact: false })).toBeVisible();
});

test("Deal Room: вкладки Чат / Условия / Документы / Платежи", async ({ page }) => {
  await page.goto("/deals/demo");
  await expect(page.getByRole("tab", { name: "Чат" })).toBeVisible();
  await page.getByRole("tab", { name: "Условия" }).click();
  await expect(page.getByText("ack заказчика и исполнителя")).toBeVisible();
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText("агрегатор")).toBeVisible();
  await page.getByRole("tab", { name: "Платежи" }).click();
  await expect(page.getByText("Прямой перевод снимает защиту")).toBeVisible();
  await page.getByRole("tab", { name: "Спор" }).click();
  await expect(page.getByText("оператор, не ИИ")).toBeVisible();
});
