import { expect, test } from "@playwright/test";

test.describe("Immersive design acceptance", () => {
  for (const width of [390, 1440]) {
    test(`home layout and search at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Нужные люди.");
      await expect(page.getByRole("link", { name: "Собрать событие" })).toHaveAttribute("href", "/events/new?event_studio_map_v1=1");
      await expect(page.locator(".reference-piece img")).toHaveCount(3);
      for (const image of await page.locator(".reference-piece img").all()) {
        await expect(image).toBeVisible();
        await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
      }
      const pieces = page.getByRole("group", { name: "Пазлы команды" });
      const dj = pieces.getByRole("button", { name: "Диджей", exact: true });
      const venue = pieces.getByRole("button", { name: "Площадка", exact: true });
      await dj.click();
      await expect(dj).toHaveAttribute("aria-pressed", "true");
      await venue.click();
      await expect(dj).toHaveAttribute("aria-pressed", "false");
      await expect(venue).toHaveAttribute("aria-pressed", "true");
      await venue.click();
      await expect(venue).toHaveAttribute("aria-pressed", "false");
      await dj.focus();
      await page.keyboard.press("Space");
      await expect(dj).toHaveAttribute("aria-pressed", "true");
      await page.keyboard.press("Escape");
      await expect(dj).toHaveAttribute("aria-pressed", "false");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.getByRole("group", { name: "Тип поиска" }).getByRole("button", { name: "Площадка", exact: true }).click();
      await expect(page.getByLabel("Гостей от")).toBeVisible();
      await expect(page.getByRole("combobox", { name: "Категория", exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "Исполнитель", exact: true }).click();
      await expect(page.getByRole("combobox", { name: "Категория", exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });
    });
  }

  test("reduced motion disables decorative entrance", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const piece = page.locator(".reference-piece").first();
    await piece.click();
    await expect(piece).toHaveAttribute("aria-pressed", "true");
    await expect(piece).toHaveCSS("transform", "none");
    await expect(piece).toHaveCSS("transition-duration", "0s");
  });
});
