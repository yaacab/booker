import { expect, test } from "@playwright/test";

test.describe("Wave 1 search / home", () => {
  test("home dual search: venue guests → catalog", async ({ page }) => {
    await page.goto("/");
    await page
      .getByRole("group", { name: "Тип поиска" })
      .getByRole("button", { name: "Площадка", exact: true })
      .click();
    await expect(page.getByLabel("Гостей от")).toBeVisible();
    await page.getByRole("button", { name: "Показать свободных" }).click();
    await expect(page).toHaveURL(/kind=venue/);
    await expect(page).toHaveURL(/guests=80/);
    await expect(page.getByRole("heading", { level: 1, name: /Каталог|Найдите свою команду/ })).toBeVisible();
  });

  test("catalog filters expose format and budget fields", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByLabel("Формат (исполнитель)")).toBeVisible();
    await expect(page.getByLabel("Бюджет до, ₽")).toBeVisible();
    await expect(page.getByLabel("Гостей от (зал)")).toBeVisible();
  });

  test("E03: research venues stay outside public search", async ({ page }) => {
    await page.goto("/search?city=Москва&kind=venue");
    await expect(page.getByText("календарь ориентировочный")).toHaveCount(0);
    await page.goto("/investor/venues");
    await expect(page.getByText(/витрина доступна только администратору/i)).toBeVisible();
  });

  test("390px catalog keeps filters and published cards reachable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByRole("heading", { level: 1, name: "Найдите свою команду" })).toBeVisible();
    await page.locator(".filter-toggle").click();
    await expect(page.getByLabel("Бюджет до, ₽")).toBeVisible();
    await expect(page.locator(".catalog-result--artist").first()).toBeVisible();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(390);
  });
});
