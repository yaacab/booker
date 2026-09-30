import { expect, test } from "@playwright/test";

test("home stays within a 390px viewport in dark and Light Edition", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const fitsViewport = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  const rightPuzzle = page.locator(".artist-first-piece.piece-3");
  await expect(rightPuzzle).toBeVisible();
  await page.locator(".artist-first-puzzles").evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished));
  });
  await expect(page.locator("html")).toHaveAttribute("data-edition", "black");
  expect(await fitsViewport()).toBe(true);

  await rightPuzzle.click();
  await expect(rightPuzzle).toHaveAttribute("aria-pressed", "true");
  await rightPuzzle.evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  expect(await fitsViewport()).toBe(true);

  await page.getByRole("button", { name: "Включить Light Edition" }).first().click();
  await expect(page.locator("html")).toHaveAttribute("data-edition", "light");
  expect(await fitsViewport()).toBe(true);
});
