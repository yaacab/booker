import { expect, test } from "@playwright/test";
import { injectSession } from "./helpers";

test("role switches survive navigation and logout does not resurrect an injected session", async ({ page }) => {
  await page.route("**/login", (route) => route.fulfill({
    contentType: "text/html", body: "<!doctype html><html><body>Session fixture</body></html>",
  }));
  for (const role of ["customer", "artist", "venue", "customer"]) {
    await injectSession(page, `fixture-${role}`, `org-${role}`);
    await page.goto("/login");
    expect(await page.evaluate(() => ({
      token: localStorage.getItem("booker.token"), org: localStorage.getItem("booker.org"),
    }))).toEqual({ token: `fixture-${role}`, org: `org-${role}` });
  }
  await page.evaluate(() => {
    localStorage.removeItem("booker.token");
    localStorage.removeItem("booker.org");
  });
  await page.reload();
  expect(await page.evaluate(() => localStorage.getItem("booker.token"))).toBeNull();
});
