import { expect, test } from "@playwright/test";
import { DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

const routes = ["/", "/search", "/login"];

for (const width of [1440, 390]) {
  test(`dark by default and Light Edition persists on public pages at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });

    for (const route of routes) {
      const response = await page.goto(route);
      expect(response?.ok()).toBe(true);
      expect(await response?.text()).toContain('<html lang="ru" data-edition="black"');
      await expect(page.locator("html")).toHaveAttribute("data-edition", "black");
      await expect(page.getByRole("button", { name: "Включить Light Edition" })).toHaveAttribute("aria-pressed", "false");
      await expect.poll(() => page.locator('meta[name="theme-color"]').evaluateAll((nodes) => nodes.length > 0 && nodes.every((node) => node.getAttribute("content") === "#101112"))).toBe(true);
      expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(16, 17, 18)");
      if (route === "/") await page.screenshot({ path: testInfo.outputPath(`home-dark-${width}.png`) });
    }

    await page.getByRole("button", { name: "Включить Light Edition" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-edition", "light");
    await expect(page.getByRole("button", { name: "Включить тёмную тему" })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => page.locator('meta[name="theme-color"]').evaluateAll((nodes) => nodes.length > 0 && nodes.every((node) => node.getAttribute("content") === "#edf1eb"))).toBe(true);
    expect(await page.evaluate(() => localStorage.getItem("booker.edition"))).toBe("light");

    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator("html")).toHaveAttribute("data-edition", "light");
      await expect(page.getByRole("button", { name: "Включить тёмную тему" })).toHaveAttribute("aria-pressed", "true");
      await expect.poll(() => page.locator('meta[name="theme-color"]').evaluateAll((nodes) => nodes.length > 0 && nodes.every((node) => node.getAttribute("content") === "#edf1eb"))).toBe(true);
      if (route === "/") await page.screenshot({ path: testInfo.outputPath(`home-light-${width}.png`) });
    }

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((item) => item.kind === "customer");
    if (!org) throw new Error("Demo customer organization is missing");
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/customer");
    await expect(page.locator('main[data-cabinet="customer"]')).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-edition", "light");
    await page.screenshot({ path: testInfo.outputPath(`cabinet-light-${width}.png`) });
    await page.getByRole("button", { name: "Включить тёмную тему" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-edition", "black");
    await page.reload();
    await expect(page.locator('main[data-cabinet="customer"]')).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-edition", "black");
    await page.screenshot({ path: testInfo.outputPath(`cabinet-dark-${width}.png`) });
    expect(await page.evaluate(() => localStorage.getItem("booker.edition"))).toBe("black");
  });
}
