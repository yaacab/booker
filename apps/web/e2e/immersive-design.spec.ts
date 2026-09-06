import { expect, test } from "@playwright/test";

test.describe("Immersive design acceptance", () => {
  for (const width of [390, 1440]) {
    test(`home layout and search at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Ваше событие.");
      await expect(page.getByRole("link", { name: "Собрать событие" })).toHaveAttribute("href", "/events/new?event_studio_map_v1=1");
      await expect(page.locator(".puzzle-art img")).toBeVisible();
      expect(await page.locator(".puzzle-art img").evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.getByRole("button", { name: "Площадка", exact: true }).click();
      await expect(page.getByLabel("Гостей от")).toBeVisible();
      await expect(page.getByLabel("Категория", { exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "Исполнитель", exact: true }).click();
      await expect(page.getByLabel("Категория", { exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });
    });
  }

  test("reduced motion disables decorative entrance", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator(".puzzle-art img")).toHaveCSS("animation-name", "none");
  });
});
