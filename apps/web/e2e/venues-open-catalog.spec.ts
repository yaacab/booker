import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth } from "./helpers";

test("исследовательские площадки отделены от каталога бронирования", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

  const catalog = await request.get(
    `${API_BASE}/catalog/search?city=${encodeURIComponent("Москва")}&kind=venue`,
  );
  expect(catalog.ok()).toBeTruthy();
  const body = await catalog.json();
  const venues = Array.isArray(body.venues) ? body.venues : [];
  expect(
    venues.filter((venue: { availability_mode?: string }) =>
      ["synthetic", "research"].includes(venue.availability_mode || ""),
    ),
  ).toHaveLength(0);
  expect(
    venues.filter((venue: { listing_origin?: string; source_type?: string }) =>
      venue.listing_origin === "open_data" || venue.source_type === "automated_import",
    ),
  ).toHaveLength(0);
  for (const venue of venues as {
    verified?: boolean;
    partnership_status?: string;
    cover_photo?: { rights_status?: string } | null;
  }[]) {
    expect(venue.verified).toBe(true);
    expect(["verified", "partner"]).toContain(venue.partnership_status);
    expect(["licensed", "official_permission"]).toContain(venue.cover_photo?.rights_status);
  }

  await page.goto("/search?city=Москва&kind=venue");
  await expect(page.getByRole("heading", { level: 1, name: "Найди место для своего события." })).toBeVisible();
  await expect(page.getByText("Это подборка из открытых источников, отдельно от бронирования в Букере.", { exact: false })).toBeVisible();

  const resultStatus = page.locator('[role="status"]', { hasText: /Найдено \d+ из \d+/ });
  await expect(resultStatus).toBeVisible();
  const statusText = (await resultStatus.textContent()) || "";
  const total = Number(statusText.match(/из (\d+)/)?.[1] || 0);
  expect(total).toBeGreaterThan(0);

  const firstCard = page.locator(".research-venue-card").first();
  await expect(firstCard).toBeVisible();
  await expect(firstCard.getByText("Доступность уточняется", { exact: true })).toBeVisible();
  await expect(firstCard.getByText("Ориентир из источника", { exact: true })).toBeVisible();
  const sourceLink = firstCard.getByRole("link", { name: "Уточнить у площадки" });
  await expect(sourceLink).toHaveAttribute("href", /^https?:\/\//);
  await expect(sourceLink).toHaveAttribute("target", "_blank");
  await expect(page.locator('.research-grid a[href^="/venues/"]')).toHaveCount(0);
});
