import { expect, test } from "@playwright/test";

test.describe("Wave 1 search / home", () => {
  test("home dual search: venue guests → catalog", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Площадка" }).click();
    await expect(page.getByLabel("Гостей от")).toBeVisible();
    await page.getByRole("button", { name: "Показать свободных" }).click();
    await expect(page).toHaveURL(/kind=venue/);
    await expect(page).toHaveURL(/guests=80/);
    await expect(page.getByRole("heading", { name: "Свободные артисты и площадки" })).toBeVisible();
  });

  test("catalog filters expose format and budget fields", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByLabel("Формат (исполнитель)")).toBeVisible();
    await expect(page.getByLabel("Бюджет до, ₽")).toBeVisible();
    await expect(page.getByLabel("Гостей от (зал)")).toBeVisible();
  });

  test("E03: synthetic venues never show confirmed-free chip as sole claim", async ({ page }) => {
    await page.goto("/search?city=Москва&kind=venue");
    const synth = page.getByText("календарь ориентировочный").first();
    await expect(synth).toBeVisible({ timeout: 20_000 });
  });
});
