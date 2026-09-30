import { expect, test } from "@playwright/test";

test.describe("Immersive home acceptance", () => {
  for (const width of [390, 1440]) {
    test(`artist-first layout and search at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");

      await expect(page.getByRole("heading", { level: 1 })).toContainText("Талант найдёт");
      await expect(page.getByRole("heading", { level: 1 })).toContainText("своё событие.");
      await expect(page.getByRole("link", { name: /Ты артист\?/ })).toHaveAttribute("href", "/for-artists");
      await expect(page.getByRole("link", { name: /Тебе нужен артист\?/ })).toHaveAttribute("href", "/search?kind=artist");

      const steps = page.getByRole("group", { name: "Как складывается выступление" });
      await expect(steps.getByRole("button")).toHaveCount(4);
      const event = steps.getByRole("button", { name: /Событие/ });
      await event.click();
      await expect(event).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#artist-first-detail")).toContainText("Выберите артиста на нужную дату");
      await expect(page.locator("#artist-first-detail").getByRole("link", { name: /Найти артиста/ })).toHaveAttribute("href", "/search?kind=artist");
      const artist = steps.getByRole("button", { name: /Артист/ });
      await artist.focus();
      await page.keyboard.press("Space");
      await expect(artist).toHaveAttribute("aria-pressed", "true");
      await expect(event).toHaveAttribute("aria-pressed", "false");

      const layout = await page.locator(".artist-first-hero, .hero-paths").evaluateAll((elements) =>
        elements.map((element) => {
          const bounds = element.getBoundingClientRect();
          return { left: bounds.left, right: bounds.right, viewport: window.innerWidth };
        }),
      );
      expect(layout).toHaveLength(2);
      for (const bounds of layout) {
        expect(bounds.left).toBeGreaterThanOrEqual(0);
        expect(bounds.right).toBeLessThanOrEqual(bounds.viewport);
      }
      await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });

      const venueLink = page.getByRole("main").getByRole("link", { name: /Подобрать площадку/ });
      await expect(venueLink).toHaveAttribute("href", "/search?kind=venue");
      await venueLink.click();
      await expect(page).toHaveURL(/\/search\?kind=venue/);
      await expect(page.getByRole("heading", { level: 1, name: "Найдите площадку для вашего события" })).toBeVisible();
      await expect(page.getByRole("radio", { name: "Площадки" })).toBeChecked();
    });
  }

  test("reduced motion keeps the puzzle interactive without entrance animation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const steps = page.getByRole("group", { name: "Как складывается выступление" });
    const event = steps.getByRole("button", { name: /Событие/ });
    await event.click();
    await expect(event).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#artist-first-detail")).toContainText("Выберите артиста на нужную дату");
    await expect(steps).toHaveCSS("animation-name", "none");
    await expect(event).toHaveCSS("animation-name", "none");
    await expect(event).toHaveCSS("transition-duration", "0s");
    await expect(event).toHaveCSS("transform", "none");
  });
});
