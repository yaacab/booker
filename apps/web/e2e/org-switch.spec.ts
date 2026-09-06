import { expect, test, type Page } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  injectSession,
  seedOrgSwitchWorkspace,
} from "./helpers";

async function switchWorkspace(page: Page, orgId: string, expectedPath: RegExp) {
  const switcher = page.getByLabel("Рабочее пространство");
  await expect(switcher).toBeVisible({ timeout: 15_000 });
  await switcher.selectOption(orgId);
  await page.waitForURL(expectedPath, { timeout: 20_000 });
  await expect(switcher).toHaveValue(orgId, { timeout: 15_000 });
}

test.describe("E15 org/role workspace switch", () => {
  test.setTimeout(120_000);

  test("переключение customer → artist → venue меняет кабинет и не утекает title", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const seed = await seedOrgSwitchWorkspace(request);

    await injectSession(page, seed.user.token, seed.customer.orgId);
    await page.goto("/cabinet/customer");

    await test.step("customer: свой title есть, чужие нет", async () => {
      await expect(page.getByRole("heading", { name: "Студия событий" })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByLabel("Рабочее пространство")).toHaveValue(seed.customer.orgId);
      await expect(page.getByText(seed.customer.eventTitle)).toBeVisible();
      await expect(page.getByText(seed.artist.eventTitle)).toHaveCount(0);
      await expect(page.getByText(seed.venue.eventTitle)).toHaveCount(0);
    });

    await test.step("switch → performer: кабинет и inbound title, без предыдущего", async () => {
      await switchWorkspace(page, seed.artist.orgId, /\/cabinet\/performer/);
      await expect(page.getByRole("heading", { name: "Календарь исполнителя" })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByLabel("Рабочее пространство")).toHaveValue(seed.artist.orgId);
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible();
      await expect(page.getByText(seed.artist.eventTitle)).toBeVisible();
      await expect(page.getByText(seed.customer.eventTitle)).toHaveCount(0);
      await expect(page.getByText(seed.venue.eventTitle)).toHaveCount(0);
    });

    await test.step("switch → venue: кабинет и inbound title, без предыдущих", async () => {
      await switchWorkspace(page, seed.venue.orgId, /\/cabinet\/venue/);
      await expect(page.getByRole("heading", { name: "Пульт площадки" })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByLabel("Рабочее пространство")).toHaveValue(seed.venue.orgId);
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible();
      await expect(page.getByText(seed.venue.eventTitle)).toBeVisible();
      await expect(page.getByText(seed.customer.eventTitle)).toHaveCount(0);
      await expect(page.getByText(seed.artist.eventTitle)).toHaveCount(0);
    });

    await test.step("switch обратно → customer: снова свой title, без supply titles", async () => {
      await switchWorkspace(page, seed.customer.orgId, /\/cabinet\/customer/);
      await expect(page.getByRole("heading", { name: "Студия событий" })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByText(seed.customer.eventTitle)).toBeVisible();
      await expect(page.getByText(seed.artist.eventTitle)).toHaveCount(0);
      await expect(page.getByText(seed.venue.eventTitle)).toHaveCount(0);
    });
  });
});
