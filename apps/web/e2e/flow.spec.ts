import { expect, test } from "@playwright/test";

test("главная: бренд и поиск", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Букер" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Показать свободных" })).toBeVisible();
});

test("юридический пакет опубликован как черновик", async ({ page }) => {
  await page.goto("/legal/offer");
  await expect(
    page.getByRole("heading", { name: "Публичная оферта цифровых услуг Букер" }),
  ).toBeVisible();
  await expect(page.getByText("не является исполнителем выступления", { exact: false })).toBeVisible();
  await expect(
    page.getByText("обе стороны подтвердили активную версию оффера", { exact: false }),
  ).toBeVisible();
});

test("Deal Room: вкладки Чат / Условия / Документы / Платежи", async ({ page }) => {
  await page.goto("/deals/demo");
  await expect(page.getByRole("tab", { name: "Чат" })).toBeVisible();
  await page.getByRole("tab", { name: "Условия" }).click();
  await expect(
    page.getByText("только после отдельных подтверждений заказчика и исполнителя"),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText("агрегатор")).toBeVisible();
  await page.getByRole("tab", { name: "Платежи" }).click();
  await expect(
    page.getByText("Прямой перевод вне предусмотренного сценария платформой не фиксируется."),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Спор" }).click();
  await expect(page.getByText("Решение принимает оператор.")).toBeVisible();
});
