import { expect, test, type Page } from "@playwright/test";
import { API_BASE, apiHealth, DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

/** V07 matrix: key public + cabinet shells across required widths. */
const VIEWPORTS = [
  { name: "320", width: 320, height: 568 },
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1440", width: 1440, height: 900 },
] as const;

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
    };
  });
  expect(
    overflow.scrollWidth,
    `horizontal overflow: scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`,
  ).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

test.describe("V07 responsive viewports (local)", () => {
  test.setTimeout(90_000);

  test("search: main landmark + keyboard reaches filters @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/search?city=Москва&kind=artist");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("main")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    const city = page.locator("#catalog-search-city");
    await city.focus();
    await expect(city).toBeFocused();
    await expect(page.getByRole("button", { name: /найти/i })).toBeVisible();
  });

  test("search: keyboard path city → find @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/search?kind=artist");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const city = page.locator("#catalog-search-city");
    await city.fill("Москва");
    await page.getByRole("button", { name: /найти/i }).focus();
    await expect(page.getByRole("button", { name: /найти/i })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/city=/);
    await expectNoHorizontalOverflow(page);
  });

  test("search → artist profile keyboard open @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/search?city=Москва&kind=artist&category=dj");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const artistLink = page.locator('a[href^="/artists/"]').first();
    await expect(artistLink).toBeVisible({ timeout: 20_000 });
    await artistLink.focus();
    await expect(artistLink).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/artists\//);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
  });

  test("search: local load timing budget @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const started = Date.now();
    await page.goto("/search?city=Москва&kind=artist", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const elapsed = Date.now() - started;
    // Local smoke budget (not Lighthouse LCP). Fail loudly if catalog shell regresses badly.
    expect(elapsed, `search shell load ${elapsed}ms`).toBeLessThan(12_000);
    const paint = await page.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      return nav ? Math.round(nav.domContentLoadedEventEnd) : null;
    });
    if (paint != null) {
      expect(paint, `domContentLoadedEventEnd=${paint}`).toBeLessThan(10_000);
    }
  });

  for (const vp of VIEWPORTS) {
    test(`home @${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/");
      await expect(page.locator("main.bk-live-home")).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    });
  }

  for (const vp of VIEWPORTS) {
    test(`search catalog @${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/search?city=Москва&kind=artist");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    });
  }

  const CABINETS = [
    { account: DEMO_ACCOUNTS.customer, orgKind: "customer" as const, path: "/cabinet/customer" },
    { account: DEMO_ACCOUNTS.artist, orgKind: "artist" as const, path: "/cabinet/performer" },
    { account: DEMO_ACCOUNTS.venue, orgKind: "venue" as const, path: "/cabinet/venue" },
  ];

  for (const vp of VIEWPORTS) {
    for (const cab of CABINETS) {
      test(`${cab.orgKind} cabinet @${vp.name}`, async ({ page, request }) => {
        test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.emulateMedia({ reducedMotion: "reduce" });

        const session = await login(request, cab.account);
        const me = await fetchMe(request, session.token);
        const org = me.organizations.find((o) => o.kind === cab.orgKind);
        if (!org) throw new Error(`Demo ${cab.orgKind} org missing — run make seed`);

        await injectSession(page, session.token, org.id);
        await page.goto(cab.path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
        await expect(page.locator("main")).toBeVisible();
        await expectNoHorizontalOverflow(page);
      });
    }
  }
});
