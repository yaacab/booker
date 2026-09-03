import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth } from "./helpers";

test("каталог площадок: open-data импорт виден с бейджем", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

  const catalog = await request.get(
    `${API_BASE}/catalog/search?city=${encodeURIComponent("Москва")}&category=venue`,
  );
  expect(catalog.ok()).toBeTruthy();
  const body = await catalog.json();
  const venues = body.venues || [];
  expect(venues.length).toBeGreaterThanOrEqual(2);
  const syntheticCount = venues.filter((v: { availability_mode?: string }) => v.availability_mode === "synthetic")
    .length;
  expect(syntheticCount).toBeGreaterThanOrEqual(1);

  await page.goto("/search?city=Москва&category=venue");
  await expect(page.getByText("календарь ориентировочный").first()).toBeVisible();
});
