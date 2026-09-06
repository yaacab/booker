import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, DEMO_PASSWORD, apiHealth } from "./helpers";

/** E01: guest search filters (+ candidate) survive login via `next` URL persistence. */
test.describe("E01 guest search → login persist", () => {
  test.setTimeout(90_000);

  test("filters set on /search survive login (next query)", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByRole("heading", { name: "Свободные артисты и площадки" })).toBeVisible();

    await page.getByLabel("Формат (исполнитель)").fill("club");
    await page.getByLabel("Бюджет до, ₽").fill("150000");
    await page.getByRole("button", { name: "Показать живых" }).click();

    await expect(page).toHaveURL(/kind=artist/);
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=150000/);

    const u = new URL(page.url());
    const returnPath = `${u.pathname}${u.search}`;
    expect(returnPath).toMatch(/\/search\?/);

    await page.goto(`/login?next=${encodeURIComponent(returnPath)}`);
    await page.locator('input[name="email"]').fill(DEMO_ACCOUNTS.customer);
    await page.locator('input[name="password"]').fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page).toHaveURL(/\/search/, { timeout: 20_000 });
    await expect(page).toHaveURL(/kind=artist/);
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=150000/);
    await expect(page.getByLabel("Формат (исполнитель)")).toHaveValue("club");
    await expect(page.getByLabel("Бюджет до, ₽")).toHaveValue("150000");
  });

  test("candidate + filter qs survive guest → login", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/search?city=Москва&kind=artist&format=club&budget_max=200000");
    await expect(page.getByRole("heading", { name: "Свободные артисты и площадки" })).toBeVisible({
      timeout: 20_000,
    });

    const artistLink = page.locator('a[href^="/artists/"]').first();
    await expect(artistLink).toBeVisible({ timeout: 20_000 });
    await artistLink.click();

    await expect(page).toHaveURL(/\/artists\//, { timeout: 15_000 });
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=200000/);
    await expect(page).toHaveURL(/kind=artist/);

    const candidateUrl = new URL(page.url());
    const returnPath = `${candidateUrl.pathname}${candidateUrl.search}`;
    const artistId = candidateUrl.pathname.split("/").pop();
    expect(artistId).toBeTruthy();

    await page.goto(`/login?next=${encodeURIComponent(returnPath)}`);
    await page.locator('input[name="email"]').fill(DEMO_ACCOUNTS.customer);
    await page.locator('input[name="password"]').fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page).toHaveURL(new RegExp(`/artists/${artistId}`), { timeout: 20_000 });
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=200000/);
    await expect(page).toHaveURL(/kind=artist/);
    await expect(page.getByRole("heading").first()).toBeVisible();
  });
});
