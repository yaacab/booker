import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth, login } from "./helpers";

type PublicVenue = {
  id: string;
  name: string;
  verified: boolean;
  availability_mode?: string;
  partnership_status?: string;
  cover_photo?: { url: string; rights_status: string } | null;
};

type ResearchVenue = { id: string; name: string };

test.describe("Wave 1 search / home", () => {
  test("главная ведёт в каталог проверенных площадок", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("main").getByRole("link", { name: /Подобрать площадку/ }).click();
    await expect(page).toHaveURL(/kind=venue/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Найдите площадку для вашего события" }),
    ).toBeVisible();
    await expect(page.locator("aside.catalog-filters")).toBeVisible();
    await expect(page.getByText("Это подборка из открытых источников", { exact: false })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Клуб Сигнал" }).first()).toBeVisible();
  });

  test("каталог артистов показывает только относящиеся к артистам фильтры", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByRole("radio", { name: "Артисты" })).toBeChecked();
    await expect(page.getByLabel("Формат (исполнитель)")).toBeVisible();
    await expect(page.getByLabel("Бюджет до, ₽")).toBeVisible();
    await expect(page.getByLabel("Гостей от", { exact: true })).toHaveCount(0);
  });

  test("research и synthetic площадки изолированы от публичного каталога", async ({ request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const admin = await login(request, "admin@booker.test");
    const researchResponse = await request.get(
      `${API_BASE}/catalog/demo/venues?city=${encodeURIComponent("Москва")}&limit=500`,
      { headers: { Authorization: `Bearer ${admin.token}` } },
    );
    expect(researchResponse.ok()).toBeTruthy();
    const research = (await researchResponse.json()) as {
      mode: string;
      count: number;
      items: ResearchVenue[];
    };
    expect(research.mode).toBe("investor_demo_research");
    expect(research.count).toBeGreaterThan(0);
    expect(research.items.length).toBe(research.count);

    const publicResponse = await request.get(
      `${API_BASE}/catalog/search?city=${encodeURIComponent("Москва")}&kind=venue`,
    );
    expect(publicResponse.ok()).toBeTruthy();
    const publicVenues = ((await publicResponse.json()) as { venues?: PublicVenue[] }).venues ?? [];
    const publicIds = new Set(publicVenues.map((venue) => venue.id));

    expect(publicVenues.some((venue) => venue.name === "Клуб Сигнал")).toBe(true);

    expect(research.items.filter((venue) => publicIds.has(venue.id))).toEqual([]);
    expect(
      publicVenues.filter((venue) =>
        ["research", "synthetic"].includes(venue.availability_mode ?? ""),
      ),
    ).toEqual([]);
    for (const venue of publicVenues) {
      expect(venue.verified, `${venue.name}: verified`).toBe(true);
      expect(venue.availability_mode, `${venue.name}: owner calendar`).toBe("owner");
      expect(["verified", "partner"], `${venue.name}: partnership`).toContain(
        venue.partnership_status,
      );
      expect(venue.cover_photo, `${venue.name}: publishable media`).toBeTruthy();
    }
  });
});
