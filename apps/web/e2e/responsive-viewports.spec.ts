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

  for (const vp of VIEWPORTS) {
    test(`search catalog @${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/search?city=Москва&kind=artist");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    });
  }

  for (const vp of VIEWPORTS) {
    test(`customer cabinet @${vp.name}`, async ({ page, request }) => {
      test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.emulateMedia({ reducedMotion: "reduce" });

      const session = await login(request, DEMO_ACCOUNTS.customer);
      const me = await fetchMe(request, session.token);
      const org = me.organizations.find((o) => o.kind === "customer");
      if (!org) throw new Error("Demo customer org missing — run make seed");

      await injectSession(page, session.token, org.id);
      await page.goto("/cabinet/customer");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
      await expect(page.locator("main")).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }
});
