import { expect, test } from "@playwright/test";

test("главная: бренд и поиск", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Букер" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Показать свободных" })).toBeVisible();
});

test("юридический пакет опубликован как черновик", async ({ page }) => {
  await page.goto("/legal/offer");
  await expect(page.getByText("не является действующей офертой", { exact: false })).toBeVisible();
  await expect(page.getByText("не является исполнителем выступления", { exact: false })).toBeVisible();
});

test("Deal Room: вкладки Чат / Условия / Документы / Платежи", async ({ page }) => {
  await page.goto("/deals/demo");
  await expect(page.getByRole("tab", { name: "Чат" })).toBeVisible();
  await page.getByRole("tab", { name: "Условия" }).click();
  await expect(page.getByText("отдельных подтверждений", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText("сохраняются в истории изменений", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Платежи" }).click();
  await expect(page.getByText("по взаимному согласию подключить гаранта", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Спор" }).click();
  await expect(page.getByText("Решение принимает оператор", { exact: false })).toBeVisible();
});

test("конструктор заявки: собирает команду мультивыбором", async ({ page }) => {
  await page.goto("/events/new");
  await page.getByRole("button", { name: "4", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Состав команды" })).toBeVisible();
  await expect(page.getByText("Выбрано: 1")).toBeVisible();

  await page.getByRole("button", { name: /Ведущий/ }).click();
  await page.getByRole("button", { name: /Музыкант/ }).click();
  await page.getByRole("button", { name: "Увеличить количество: Музыкант" }).click();
  await expect(page.getByText("Выбрано: 4")).toBeVisible();

  await page.getByPlaceholder("Например, иллюзионист").fill("Фокусник");
  await page.getByRole("button", { name: "Добавить", exact: true }).click();
  await expect(page.getByRole("button", { name: /Фокусник/ })).toBeVisible();
  await expect(page.getByText("Выбрано: 5")).toBeVisible();
});
