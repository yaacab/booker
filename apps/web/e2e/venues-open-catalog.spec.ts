import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth } from "./helpers";

test("публичный каталог содержит только готовые к бронированию площадки", async ({ page, request }) => {
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
  expect(venues.some((venue: { name?: string }) => venue.name === "Клуб Сигнал")).toBe(true);
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
  await expect(
    page.getByRole("heading", { level: 1, name: "Найдите площадку для вашего события" }),
  ).toBeVisible();
  await expect(page.getByText("Это подборка из открытых источников", { exact: false })).toHaveCount(0);
  await expect(page.locator(".catalog-count")).toContainText(/\d+ вариант/);

  const signal = page.locator("article.catalog-result--venue", { hasText: "Клуб Сигнал" });
  await expect(signal).toBeVisible();
  await expect(signal.getByText("Профиль подтверждён", { exact: true })).toBeVisible();
  await expect(signal.getByRole("link", { name: "Клуб Сигнал", exact: true })).toHaveAttribute(
    "href",
    /^\/venues\//,
  );
  await expect(page.locator(".research-venue-card")).toHaveCount(0);
});
