import { expect, test, type Page } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  DEMO_ACCOUNTS,
  fetchMe,
  injectSession,
  login,
  seedNegotiation,
  seedRequestAwaitingOffer,
} from "./helpers";

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
    const metrics = await page.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      const paints = performance.getEntriesByType("paint") as PerformanceEntry[];
      const fcp = paints.find((p) => p.name === "first-contentful-paint");
      return {
        domContentLoadedEventEnd: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
        responseEnd: nav ? Math.round(nav.responseEnd) : null,
        transferSize: nav && "transferSize" in nav ? Number(nav.transferSize) : null,
        fcp: fcp ? Math.round(fcp.startTime) : null,
      };
    });
    if (metrics.domContentLoadedEventEnd != null) {
      expect(metrics.domContentLoadedEventEnd, `domContentLoadedEventEnd=${metrics.domContentLoadedEventEnd}`).toBeLessThan(10_000);
    }
    if (metrics.fcp != null) {
      expect(metrics.fcp, `fcp=${metrics.fcp}`).toBeLessThan(8_000);
    }
    // Persist local evidence for V07 review (not a substitute for Lighthouse/HAR on staging).
    const fs = await import("node:fs");
    const path = await import("node:path");
    const out = path.resolve(__dirname, "../../../docs/ops/V07_LOCAL_PERF_SMOKE_2026-11-03.json");
    fs.writeFileSync(
      out,
      JSON.stringify({ captured_at: new Date().toISOString(), route: "/search?city=Москва&kind=artist", viewport: "390x844", elapsed_ms: elapsed, ...metrics }, null, 2),
    );
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

  test("keyboard chain: search → profile → cabinet @390", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });

    await page.goto("/search?city=Москва&kind=artist&category=dj");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const artistLink = page.locator('a[href^="/artists/"]').first();
    await expect(artistLink).toBeVisible({ timeout: 20_000 });
    await artistLink.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/artists\//);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    if (!org) throw new Error("Demo customer org missing — run make seed");
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/customer");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("keyboard chain unified: search → profile → requests → deal @390", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });

    await page.goto("/search?city=Москва&kind=artist&category=dj");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const artistLink = page.locator('a[href^="/artists/"]').first();
    await expect(artistLink).toBeVisible({ timeout: 20_000 });
    await artistLink.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/artists\//);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);

    const ctx = await seedRequestAwaitingOffer(request);
    await injectSession(page, ctx.ownerToken, ctx.artistOrgId);
    await page.goto("/cabinet/performer/requests");
    await expect(page.getByTestId("performer-requests-inbox")).toBeVisible({ timeout: 15_000 });
    const pick = page.getByRole("button", { name: new RegExp(ctx.eventTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
    await expect(pick).toBeVisible({ timeout: 15_000 });
    await pick.focus();
    await page.keyboard.press("Enter");
    await page.getByLabel(/сумма вашего предложения/i).fill("91000");
    const createOffer = page.getByRole("button", { name: /создать предложение/i });
    await createOffer.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/deals\//, { timeout: 20_000 });
    await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
    await expectNoHorizontalOverflow(page);
  });

  test("keyboard chain: cabinet request → deal room @390", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });

    const ctx = await seedRequestAwaitingOffer(request);
    await injectSession(page, ctx.ownerToken, ctx.artistOrgId);
    await page.goto("/cabinet/performer/requests");
    await expect(page.getByTestId("performer-requests-inbox")).toBeVisible({ timeout: 15_000 });
    const pick = page.getByRole("button", { name: new RegExp(ctx.eventTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
    await expect(pick).toBeVisible({ timeout: 15_000 });
    await pick.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: ctx.eventTitle })).toBeVisible();
    const amount = page.getByLabel(/сумма вашего предложения/i);
    await amount.focus();
    await amount.fill("90000");
    const createOffer = page.getByRole("button", { name: /создать предложение/i });
    await createOffer.focus();
    await expect(createOffer).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/deals\//, { timeout: 20_000 });
    await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("deal room: landmark + no overflow + Tab @390", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const negotiation = await seedNegotiation(request, {
      honorariumRub: 77_000,
      terms: "V07 deal room viewport",
      slotStartsAt: "2026-12-15T18:00:00+00:00",
      slotEndsAt: "2026-12-15T22:00:00+00:00",
    });
    await injectSession(page, negotiation.customer.token, negotiation.customer.orgId);
    await page.goto(`/deals/${negotiation.bookingId}`);
    await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("main")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  for (const vp of VIEWPORTS) {
    test(`login shell @${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/login");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
      await expect(page.locator("main, form").first()).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }

  test("login: keyboard reaches email @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const email = page.getByLabel(/email|почта|e-mail/i).first();
    await email.focus();
    await expect(email).toBeFocused();
  });

  for (const vp of [
    { name: "390", width: 390, height: 844 },
    { name: "1440", width: 1440, height: 900 },
  ] as const) {
    test(`artist profile from catalog @${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/search?city=Москва&kind=artist&category=dj");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
      const artistLink = page.locator('a[href^="/artists/"]').first();
      await expect(artistLink).toBeVisible({ timeout: 20_000 });
      await artistLink.click();
      await expect(page).toHaveURL(/\/artists\//);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    });
  }

  test("compare shell no overflow @390", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/compare");
    await expect(page.locator("main, h1").first()).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
  });

  test("legal offer no overflow @320", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/legal/offer");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
  });

  for (const route of [
    { path: "/faq", name: "faq" },
    { path: "/for-artists", name: "for-artists" },
    { path: "/support", name: "support public" },
    { path: "/legal/privacy", name: "legal privacy" },
    { path: "/assemble", name: "assemble" },
    { path: "/briefs", name: "briefs" },
    { path: "/investor/venues", name: "investor venues" },
  ] as const) {
    test(`${route.name} no overflow @390`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(route.path);
      await expect(page.locator("main, h1").first()).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    });
  }

  test("event studio new: no overflow @320", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    await page.setViewportSize({ width: 320, height: 568 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    if (!org) throw new Error("Demo customer org missing — run make seed");
    await injectSession(page, session.token, org.id);
    await page.goto("/events/new");
    await expect(page.locator("main, form, h1").first()).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
  });
});
