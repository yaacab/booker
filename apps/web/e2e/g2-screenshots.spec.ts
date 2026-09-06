import { expect, test } from "@playwright/test";
import path from "node:path";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

const OUT_DIR = path.resolve(__dirname, "../../../docs/screenshots/g2-roles");

const ROLES = [
  {
    key: "customer",
    email: DEMO_ACCOUNTS.customer,
    orgKind: "customer",
    route: "/cabinet/customer",
    heading: "Студия событий",
  },
  {
    key: "performer",
    email: DEMO_ACCOUNTS.artist,
    orgKind: "artist",
    route: "/cabinet/performer",
    heading: "Календарь исполнителя",
  },
  {
    key: "venue",
    email: DEMO_ACCOUNTS.venue,
    orgKind: "venue",
    route: "/cabinet/venue",
    heading: "Пульт площадки",
  },
] as const;

const VIEWPORTS = [
  { label: "1440", width: 1440, height: 900 },
  { label: "390", width: 390, height: 844 },
] as const;

test.describe("G2 role cabinet screenshots", () => {
  test.setTimeout(180_000);

  test("customer / performer / venue at 1440 and 390", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    for (const role of ROLES) {
      const session = await login(request, role.email);
      const me = await fetchMe(request, session.token);
      const org = me.organizations.find((o) => o.kind === role.orgKind);
      expect(org?.id, `demo org for ${role.key}`).toBeTruthy();

      await injectSession(page, session.token, org!.id);

      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.goto(role.route);
        await expect(page.getByRole("heading", { level: 1, name: role.heading })).toBeVisible({
          timeout: 20_000,
        });
        await expect(page.locator(`main[data-cabinet="${role.key}"]`)).toBeVisible();
        await expect(page.getByRole("button", { name: "Выйти из аккаунта" })).toBeVisible({
          timeout: 15_000,
        });
        await page.waitForTimeout(500);

        const file = path.join(OUT_DIR, `${role.key}-${vp.label}.png`);
        await page.screenshot({ path: file, fullPage: true });
      }
    }
  });
});
