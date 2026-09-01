import { expect, test } from "@playwright/test";

test.describe("Event Studio Map v1", () => {
  test("классический мастер по умолчанию", async ({ page }) => {
    await page.goto("/events/new");
    await expect(page.getByRole("heading", { name: "Новая заявка" })).toBeVisible();
    await expect(page.getByText("Event Studio · 8 шагов")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Соберите событие" })).toHaveCount(0);
  });

  test("feature flag включает карту события", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.getByRole("heading", { name: "Соберите событие" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Основное" })).toHaveCount(0);
    await expect(page.getByRole("status")).toContainText(/Сохран/i);
    await expect(page.getByLabel("Этапы создания события")).toBeVisible();
    await expect(page.getByLabel("Карта события")).toBeVisible();
  });

  test("навигация по этапам и черновик", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=1");
    await page.getByLabel("Название события").fill("E2E Studio Map");
    await page.getByRole("button", { name: "Проверка" }).click();
    await expect(page.getByRole("button", { name: /Продолжить/ })).toBeVisible();
    await expect(page.getByText("Ориентир бюджета")).toBeVisible();
  });

  test("mobile: sticky summary и bottom sheet toggle", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/events/new?event_studio_map_v1=1");
    const toggle = page.locator(".mobile-panel-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByRole("complementary", { name: "Добавить исполнителя" })).toBeVisible();
    await expect(page.getByLabel("Поиск исполнителя")).toBeVisible();
    await page.getByLabel("Закрыть каталог исполнителей").click();
    await expect(toggle).toBeVisible();
  });

  test("screenshots desktop 1440 и mobile 390", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/events/new?event_studio_map_v1=1");
    await page.getByLabel("Название события").fill("Свадьба · демо");
    await page.screenshot({ path: "../../docs/screenshots/event-studio-map-v1/desktop-1440.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "../../docs/screenshots/event-studio-map-v1/mobile-390.png", fullPage: true });
  });
});
