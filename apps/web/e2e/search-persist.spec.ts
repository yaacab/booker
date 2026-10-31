import { expect, test, type Page } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, DEMO_PASSWORD, apiHealth } from "./helpers";

/** UI login with retry — parallel e2e often hits auth rate limit. */
async function loginWithNext(page: Page, nextPath: string, expectedUrl: RegExp) {
  await page.goto(`/login?next=${encodeURIComponent(nextPath)}`);
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.locator('input[name="email"]').fill(DEMO_ACCOUNTS.customer);
    await page.locator('input[name="password"]').fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: "Войти" }).click();
    try {
      await page.waitForURL(expectedUrl, { timeout: 12_000 });
      return;
    } catch {
      const limited = await page.getByText(/Слишком много запросов/i).isVisible().catch(() => false);
      if (!limited && attempt === 5) throw new Error(`login did not reach ${expectedUrl}`);
      if (!limited) {
        // brief settle then retry once more if still on login
        if (!page.url().includes("/login")) throw new Error(`unexpected url after login: ${page.url()}`);
      }
      await page.waitForTimeout(2500 * (attempt + 1));
      if (!page.url().includes("/login")) {
        await page.goto(`/login?next=${encodeURIComponent(nextPath)}`);
      }
    }
  }
  throw new Error(`login exhausted retries for next=${nextPath}`);
}

/** E01: guest search filters (+ candidate) survive login via `next` URL persistence. */
test.describe("E01 guest search → login persist", () => {
  test.setTimeout(120_000);

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

    await loginWithNext(page, returnPath, /\/search/);

    await expect(page).toHaveURL(/kind=artist/);
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=150000/);
    await expect(page.getByLabel("Формат (исполнитель)")).toHaveValue("club");
    await expect(page.getByLabel("Бюджет до, ₽")).toHaveValue("150000");
  });

  test("candidate + filter qs survive guest → login", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    await page.setViewportSize({ width: 1440, height: 900 });
    // Start without format filter so seed artists with open slots are listed, then apply filters.
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByRole("heading", { name: "Свободные артисты и площадки" })).toBeVisible({
      timeout: 20_000,
    });

    const artistLink = page.locator('a[href^="/artists/"]').first();
    await expect(artistLink).toBeVisible({ timeout: 20_000 });

    await page.getByLabel("Формат (исполнитель)").fill("club");
    await page.getByLabel("Бюджет до, ₽").fill("200000");
    await page.getByRole("button", { name: "Показать живых" }).click();
    await expect(page).toHaveURL(/format=club/);
    await expect(page).toHaveURL(/budget_max=200000/);

    // Prefer a club-filtered card; fall back without format if CI seed has no club matches.
    const filteredLink = page.locator('a[href^="/artists/"]').first();
    const hasFiltered = await filteredLink
      .waitFor({ state: "visible", timeout: 12_000 })
      .then(() => true)
      .catch(() => false);
    if (!hasFiltered) {
      await page.goto("/search?city=Москва&kind=artist&budget_max=200000");
      await expect(page.locator('a[href^="/artists/"]').first()).toBeVisible({ timeout: 20_000 });
    }
    await page.locator('a[href^="/artists/"]').first().click();

    await expect(page).toHaveURL(/\/artists\//, { timeout: 15_000 });
    await expect(page).toHaveURL(/kind=artist/);
    await expect(page).toHaveURL(/budget_max=200000/);

    const candidateUrl = new URL(page.url());
    const returnPath = `${candidateUrl.pathname}${candidateUrl.search}`;
    const artistId = candidateUrl.pathname.split("/").pop();
    expect(artistId).toBeTruthy();

    await loginWithNext(page, returnPath, new RegExp(`/artists/${artistId}`));

    await expect(page).toHaveURL(/budget_max=200000/);
    await expect(page).toHaveURL(/kind=artist/);
    await expect(page.getByRole("heading").first()).toBeVisible();
  });
});
