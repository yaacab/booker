import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth, injectSession, seedRequestAwaitingOffer } from "./helpers";

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

test("заявка → оффер: API seed, artist cabinet, Deal Room", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

  const ctx = await seedRequestAwaitingOffer(request);
  await injectSession(page, ctx.ownerToken, ctx.artistOrgId);

  await page.goto("/cabinet");
  await expect(page.getByRole("heading", { name: "Входящие заявки" })).toBeVisible();
  await expect(page.getByText(ctx.eventTitle)).toBeVisible();
  await page.getByRole("button", { name: "Отправить предложение" }).click();

  await expect(page).toHaveURL(/\/deals\//, { timeout: 15_000 });
  await expect(page.getByRole("tab", { name: "Чат" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Условия" })).toBeVisible();
});

test("Deal Room: вкладки Сводка / Чат / Условия / Документы / Платежи", async ({ page }) => {
  await page.goto("/deals/demo");
  await expect(page.getByRole("tab", { name: "Сводка" })).toBeVisible();
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
