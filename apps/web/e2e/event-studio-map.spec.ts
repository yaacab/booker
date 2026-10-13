import { expect, test } from "@playwright/test";

test.describe("Event Studio Map v1", () => {
  test("классический мастер доступен как rollback", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=0");
    await expect(page.getByRole("heading", { name: "Новая заявка" })).toBeVisible();
    await expect(page.getByText("Event Studio · 8 шагов")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Соберите событие" })).toHaveCount(0);
  });

  test("карта события включена по умолчанию", async ({ page }) => {
    await page.goto("/events/new");
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Соберите событие", exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Основное" })).toHaveCount(0);
    await expect(page.getByRole("status")).toContainText(/Сохран/i);
    await expect(page.getByLabel("Этапы создания события")).toBeVisible();
    await expect(page.getByLabel("Карта события")).toBeVisible();
  });

  test("навигация по этапам и черновик", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await page.getByLabel("Название события").fill("E2E Studio Map");
    await page.getByRole("button", { name: "Проверка" }).click();
    await expect(page.getByRole("button", { name: /Продолжить/ })).toBeVisible();
    await expect(page.getByText("Бюджет заказчика")).toBeVisible();
  });

  test("разделы открываются в любом порядке, бюджет не ломает цифры", async ({ page }) => {
    await page.goto("/events/new");
    await expect(page.getByRole("navigation", { name: "Разделы события" })).toBeVisible();

    await page.getByRole("button", { name: "Бюджет", exact: true }).click();
    await page.getByLabel("Бюджет, ₽").fill("250000");
    await expect(page.getByLabel("Бюджет, ₽")).toHaveValue("250000");

    await page.getByRole("button", { name: "Райдер", exact: true }).click();
    await page.getByRole("checkbox", { name: /Звук и свет/ }).uncheck();

    await page.getByRole("button", { name: "Дата и время", exact: true }).click();
    await page.getByRole("button", { name: "Дата", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("button", { name: "Следующий месяц" })).toBeVisible();
    await page.getByRole("button", { name: "Закрыть выбор" }).click();

    await page.getByRole("button", { name: "Начало", exact: true }).click();
    await expect(page.getByRole("listbox", { name: "Часы" })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Минуты" })).toBeVisible();
  });

  test("профильная ссылка заранее выбирает артиста и площадку", async ({ page }) => {
    await page.route("**/catalog/search?*", async (route) => {
      await route.fulfill({
        json: {
          items: [
            {
              id: "artist-direct",
              name: "Артист из профиля",
              city: "Москва",
              category: "dj",
              verified: true,
              open_slots: 1,
              tariffs: [{ honorarium_rub: 80000 }],
            },
          ],
          venues: [
            {
              id: "venue-direct",
              name: "Площадка из профиля",
              city: "Москва",
              category: "venue",
              tariffs: [{ honorarium_rub: 120000 }],
            },
          ],
        },
      });
    });
    await page.goto("/events/new?artist=artist-direct&venue=venue-direct");
    await expect(page.getByText("Артист из профиля", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Площадка из профиля", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("80 000–102 400 ₽", { exact: false })).toHaveCount(0);
    await expect(page.getByText(/200 000–256 000 ₽/)).toBeVisible();
  });

  test("mobile: sticky summary и bottom sheet toggle", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/events/new?event_studio_map_v1=1");
    const toggle = page.locator(".mobile-panel-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByRole("complementary", { name: "Добавить исполнителя" })).toBeVisible();
    await expect(page.getByLabel("Поиск исполнителя")).toBeVisible();
    await page.getByLabel("Закрыть панель").click();
    await expect(toggle).toBeVisible();
  });

  test("E06: autosave переживает reload", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await page.getByLabel("Название события").fill("Autosave E06");
    await expect
      .poll(async () => page.evaluate(() => localStorage.getItem("booker.eventStudioMapDraft") || ""), {
        timeout: 5_000,
      })
      .toContain("Autosave E06");
    await page.reload();
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await expect(page.getByLabel("Название события")).toHaveValue("Autosave E06");
  });

  test("screenshots desktop 1440 и mobile 390", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await page.getByLabel("Название события").fill("Свадьба · демо");
    await page.screenshot({ path: "../../docs/screenshots/event-studio-map-v1/desktop-1440.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("complementary", { name: "Добавить исполнителя" })).toBeHidden();
    await page.screenshot({ path: "../../docs/screenshots/event-studio-map-v1/mobile-390.png", fullPage: true });
  });
});
